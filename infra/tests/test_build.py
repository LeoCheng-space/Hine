"""build.sh orchestration: real sh, real repo scripts and Python helpers; external commands are recorded shims.

No Docker daemon, sudo, package manager or network access is used.
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
SH = shutil.which("sh")
REAL_TOOLS = ("sh", "python3", "sed", "awk", "tr", "grep", "cat", "mkdir", "chmod", "install", "mktemp", "rm", "mv",
              "cp", "find", "diff", "date", "tail", "head", "cut", "env", "stat", "uname", "sha256sum", "dirname",
              "basename", "openssl", "ls", "touch", "sort", "wc")
SHIMS = {
    "docker": r'''
printf 'docker %s\n' "$*" >> "$FAKE_LOG"
case "$1" in
  info) [ "${FAKE_DOCKER_INFO:-ok}" = ok ] ;;
  ps) [ -z "${FAKE_DOCKER_PS:-}" ] || printf '%s\n' "$FAKE_DOCKER_PS" ;;
  network)
    case "$2" in
      ls) [ -z "${FAKE_NETWORK_IDS:-}" ] || printf '%s\n' "$FAKE_NETWORK_IDS" ;;
      inspect) cat "$FAKE_NETWORKS_JSON" ;;
    esac ;;
  volume) [ "${FAKE_VOLUME_EXISTS:-0}" = 1 ] ;;
  compose)
    case "$2" in
      version) printf '%s\n' "${FAKE_COMPOSE_VERSION:-2.29.1}" ;;
      *) exit "${FAKE_COMPOSE_STATUS:-0}" ;;
    esac ;;
esac
''',
    "sudo": r'''
printf 'sudo %s\n' "$*" >> "$FAKE_LOG"
case "$*" in *"$FAKE_SRV"*) exec "$@" ;; esac
exit 0
''',
    "sg": r'''
printf 'sg %s\n' "$*" >> "$FAKE_LOG"
printf '%s' "$3" > "$FAKE_SG_COMMAND"
[ ! -e "$FAKE_ROOT/.build.lock" ] || printf 'lock-present\n' >> "$FAKE_LOG"
exec sh -c "$3"
''',
    "id": r'''
if [ "${1:-}" = -nG ]; then printf '%s\n' "${FAKE_GROUPS:-docker}"; exit 0; fi
exec "$REAL_ID" "$@"
''',
    "getent": r'''
[ -n "${FAKE_GETENT:-}" ] || exit 2
printf '%b' "$FAKE_GETENT"
''',
    "ss": r'''
[ "${FAKE_SS_LISTEN:-0}" = 1 ] && printf 'LISTEN 0 4096 0.0.0.0:443 0.0.0.0:*\n'
exit 0
''',
    "git": r'''
case "$*" in *rev-parse*) printf '%s\n' "${FAKE_COMMIT:-0123456789ab}" ;; esac
''',
    "bun": r'''
printf 'bun %s\n' "$*" >> "$FAKE_LOG"
case "$1" in
  --version) printf '1.4.2\n' ;;
  run) mkdir -p dist/assets
       printf '<html>%s</html>\n' "$PUBLIC_ORIGIN" > dist/index.html
       printf 'asset\n' > dist/assets/app.js ;;
esac
''',
    "curl": r'''
printf 'curl %s\n' "$*" >> "$FAKE_LOG"
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then printf 'not-the-bun-release' > "$2"; shift; fi
  shift
done
''',
    "apt-get": "printf 'apt-get %s\\n' \"$*\" >> \"$FAKE_LOG\"\n",
    "usermod": "printf 'usermod %s\\n' \"$*\" >> \"$FAKE_LOG\"\n",
    "systemctl": "printf 'systemctl %s\\n' \"$*\" >> \"$FAKE_LOG\"\n",
    "dpkg": "printf 'amd64\\n'\n",
    "unzip": "printf 'unzip %s\\n' \"$*\" >> \"$FAKE_LOG\"\n",
}
OPERATION_STUB = r'''#!/bin/sh
printf '%s %s | WEB_ROOT=%s HINE_ENV=%s PROJECT=%s TRUSTED=%s SECRETS=%s\n' "$(basename "$0")" "$*" \
  "${WEB_ROOT:-}" "${HINE_ENV:-}" "${COMPOSE_PROJECT_NAME:-}" "${TRUSTED_PROXY_NETWORKS:-}" "${HINE_SECRET_DIR:-}" >> "$FAKE_LOG"
case "$(basename "$0") $*" in "${FAKE_FAIL_OPERATION:-<none>}") echo 'stub failure detail'; exit 1 ;; esac
if [ "$(basename "$0")" = backup-postgres.sh ]; then : > "$2"; fi
'''
DEPLOY = "HINE_DOMAIN={domain}\nACME_EMAIL=ops@example.org\nHINE_EXPECTED_IP=34.80.10.20\n"
ANSWERS = "34.80.10.20 STREAM {domain}\\n34.80.10.20 DGRAM\\n"


class BuildScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "repo with 'quote"
        self.root.mkdir()
        for name in ("build.sh", "deploy.env.example", ".env.example", "docker-compose.yml"):
            shutil.copyfile(SOURCE / name, self.root / name)
        shutil.copytree(SOURCE / "infra", self.root / "infra", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "frontend/app").mkdir(parents=True)
        self.srv = base / "srv"
        self.home = base / "home"
        self.home.mkdir()
        self.log = base / "calls.log"
        self.log.touch()
        self.bin = base / "bin"
        self.bin.mkdir()
        for tool in REAL_TOOLS:
            (self.bin / tool).symlink_to(shutil.which(tool))
        for name, body in SHIMS.items():
            shim = self.bin / name
            shim.write_text("#!/bin/sh\n" + body)
            shim.chmod(0o755)
        self.os_release = base / "os-release"
        self.os_release.write_text('ID=ubuntu\nVERSION_CODENAME=noble\n')
        self.networks = base / "networks.json"
        self.networks.write_text("[]")
        self.sg_command = base / "sg-command"
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.home), "LANG": "C.UTF-8",
            "FAKE_LOG": str(self.log), "FAKE_ROOT": str(self.root), "FAKE_SRV": str(self.srv),
            "FAKE_SG_COMMAND": str(self.sg_command), "FAKE_NETWORKS_JSON": str(self.networks),
            "REAL_ID": shutil.which("id"), "HINE_PRODUCTION_HOME": str(self.srv), "HINE_OS_RELEASE": str(self.os_release),
        }

    def tearDown(self):
        self.temp.cleanup()

    def build(self, *args, **overrides):
        environment = dict(self.env)
        environment.update({key: str(value) for key, value in overrides.items()})
        return subprocess.run([SH, str(self.root / "build.sh"), *args], cwd=self.root, env=environment,
                              text=True, capture_output=True, check=False)

    def calls(self):
        return self.log.read_text().splitlines()

    def index(self, prefix):
        for position, line in enumerate(self.calls()):
            if line.startswith(prefix):
                return position
        self.fail(f"no call starting with {prefix!r} in:\n" + self.log.read_text())

    def production(self, domain="hine.example.org"):
        for name in ("stack.sh", "preflight.sh", "backup-postgres.sh"):
            (self.root / "infra/scripts" / name).write_text(OPERATION_STUB)
        (self.root / "deploy.env").write_text(DEPLOY.format(domain=domain))
        return {"FAKE_GETENT": ANSWERS.format(domain=domain)}

    # Arguments, help and locking -------------------------------------------------------------
    def test_unknown_or_misplaced_arguments_print_usage(self):
        for arguments in (("--prod",), ("status", "--follow"), ("stop", "logs"), ("logs", "api", "redis")):
            with self.subTest(arguments=arguments):
                result = self.build(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn("用法", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_existing_lock_stops_after_prerequisites_without_removing_it(self):
        (self.root / ".build.lock").mkdir()
        (self.root / ".build.lock/pid").write_text("4242\n")
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn("已有另一個 build.sh 在執行（PID 4242）", result.stderr)
        self.assertTrue((self.root / ".build.lock/pid").exists())

    def test_docker_group_switch_happens_before_locking_with_quoted_path(self):
        result = self.build("--production", FAKE_DOCKER_INFO="fail", FAKE_GROUPS="users")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("已切換到 docker 群組", result.stderr)
        self.assertTrue(any(line.startswith("sudo usermod -aG docker ") for line in self.calls()))
        # sg makes docker the primary group; switching back keeps created files owned by the user's own group
        # (otherwise existing .secrets owned by user:user are rejected), while docker stays supplementary.
        primary = subprocess.run([shutil.which("id"), "-gn"], text=True, capture_output=True, check=True).stdout.strip()
        self.assertTrue(any(line.startswith(f"sg docker -c sg {primary} -c ") for line in self.calls()), self.log.read_text())
        self.assertNotIn("lock-present", self.calls())
        command = self.sg_command.read_text()
        quoted = "'" + str(self.root).replace("'", "'\\''") + "/build.sh'"
        self.assertTrue(command.startswith("HINE_BUILD_REEXEC=1 HINE_BUILD_LOG='"), command)
        self.assertTrue(command.endswith(" sh " + quoted + " --production"), command)
        self.assertFalse((self.root / ".build.lock").exists())

    # Local mode --------------------------------------------------------------------------------
    def test_local_run_initializes_builds_with_local_origin_and_waits(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://localhost:8443", result.stdout)
        self.assertIn("https://localhost:8443", (self.root / "frontend/app/dist/index.html").read_text())
        self.assertTrue((self.root / ".secrets/database_url").is_file())
        up = self.calls()[self.index("docker compose --project-directory")]
        self.assertIn("compose.local.yml", up)
        self.assertIn("--profile local up -d --build --wait --wait-timeout 180", up)
        self.assertFalse((self.root / ".build.lock").exists())
        logs = list((self.root / ".build-logs").iterdir())
        self.assertEqual(len(logs), 1)
        self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)

    def test_local_port_owned_by_own_caddy_allows_in_place_rerun(self):
        result = self.build(FAKE_DOCKER_PS="hine-dev-caddy-1|hine-dev|caddy")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_port_owned_by_another_stack_or_process_stops_before_start(self):
        for overrides, fragment in (({"FAKE_DOCKER_PS": "old-caddy-1|hine-manual-acceptance|caddy"}, "hine-manual-acceptance"),
                                    ({"FAKE_SS_LISTEN": "1"}, "其他程式")):
            with self.subTest(fragment=fragment):
                self.log.write_text("")
                result = self.build(**overrides)
                self.assertEqual(result.returncode, 1)
                self.assertIn(fragment, result.stderr)
                self.assertFalse(any(" up -d " in line for line in self.calls()))

    # Prerequisites -----------------------------------------------------------------------------
    def test_debian_installs_docker_from_the_official_repository_in_order(self):
        (self.bin / "docker").unlink()
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Docker Compose v2.20", result.stderr)
        order = [self.index("sudo apt-get update"),
                 self.index("sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates"),
                 self.index("sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg"),
                 self.index("sudo install -m 0644"),
                 self.index("sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce")]
        self.assertEqual(order, sorted(order))

    def test_other_systems_get_instructions_without_sudo(self):
        (self.bin / "docker").unlink()
        self.os_release.write_text("ID=fedora\n")
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn("https://docs.docker.com/engine/install/", result.stderr)
        self.assertFalse(any(line.startswith("sudo") for line in self.calls()))

    def test_bun_download_with_wrong_checksum_is_not_installed(self):
        (self.bin / "bun").unlink()
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn("SHA-256 不符", result.stderr)
        self.assertFalse((self.home / ".local/share/hine/bun-1.4.2/bun").exists())

    # Production mode ---------------------------------------------------------------------------
    def test_missing_deploy_env_creates_private_template_and_stops(self):
        result = self.build("--production")
        self.assertEqual(result.returncode, 1)
        self.assertIn("HINE_DOMAIN", result.stderr)
        self.assertEqual(stat.S_IMODE((self.root / "deploy.env").stat().st_mode), 0o600)
        self.assertFalse(self.srv.exists())

    def test_invalid_deploy_env_and_dns_mismatch_stop_before_any_directory_or_service(self):
        overrides = self.production()
        (self.root / "deploy.env").write_text("HINE_DOMAIN=$(id)\n")
        result = self.build("--production", **overrides)
        self.assertEqual(result.returncode, 1)
        self.assertIn("不允許的字元", result.stderr)
        self.production()
        result = self.build("--production", FAKE_GETENT="34.80.10.20 STREAM x\\n2001:db8::1 STREAM x\\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DNS 預檢未通過", result.stderr)
        self.assertFalse(self.srv.exists())
        self.assertFalse(any(line.startswith("stack.sh") for line in self.calls()))

    def test_subnet_checks_ignore_own_identical_networks_only(self):
        overrides = self.production()
        own = ('{"Name":"hine-production_edge","Labels":{"com.docker.compose.project":"hine-production",'
               '"com.docker.compose.network":"edge"},"IPAM":{"Config":[{"Subnet":"SUBNET"}]}}')
        for subnet, expected in (("172.30.1.0/24", 0), ("172.31.1.0/24", 1)):
            with self.subTest(subnet=subnet):
                self.networks.write_text("[" + own.replace("SUBNET", subnet) + "]")
                result = self.build("--production", FAKE_NETWORK_IDS="abc123", **overrides)
                self.assertEqual(result.returncode, expected, result.stderr)
        self.networks.write_text('[{"Name":"other_net","Labels":{},"IPAM":{"Config":[{"Subnet":"172.30.0.0/16"}]}}]')
        result = self.build("--production", FAKE_NETWORK_IDS="abc123", **overrides)
        self.assertEqual(result.returncode, 1)
        self.assertIn("other_net", result.stderr)

    def test_first_production_deploy_creates_layout_and_records_active_release(self):
        overrides = self.production()
        result = self.build("--production", **overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        modes = {path: stat.S_IMODE((self.srv / path).stat().st_mode)
                 for path in ("", "releases", "secrets", "backups")}
        self.assertEqual(modes, {"": 0o755, "releases": 0o755, "secrets": 0o700, "backups": 0o700})
        web = self.srv / "releases/0123456789ab/web"
        self.assertIn("https://hine.example.org", (web / "index.html").read_text())
        self.assertEqual(stat.S_IMODE((web / "index.html").stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE((web / "assets").stat().st_mode), 0o755)
        self.assertTrue((self.srv / "secrets/jwt_signing_key").is_file())
        self.assertFalse((self.root / ".secrets").exists())
        self.assertIn(f"HINE_RUNTIME_UID={os.getuid()}\n", (self.root / ".env").read_text())
        migrate = self.calls()[self.index("stack.sh migrate")]
        self.assertIn(f"WEB_ROOT={web} HINE_ENV=production PROJECT=hine-production", migrate)
        self.assertIn("TRUSTED=172.30.1.0/24,172.30.2.0/24", migrate)
        self.assertIn(f"SECRETS={self.srv}/secrets", migrate)
        self.assertLess(self.index("preflight.sh --local"), self.index("stack.sh migrate"))
        self.assertLess(self.index("stack.sh up -d --build --wait"), self.index("preflight.sh --public"))
        self.assertFalse(any(line.startswith("backup-postgres.sh") for line in self.calls()))
        active = (self.srv / "active.env").read_text()
        self.assertIn("HINE_ACTIVE_COMMIT=0123456789ab\n", active)
        self.assertIn(f"WEB_ROOT={web}\n", active)

    def test_upgrade_backs_up_after_stopping_writers_and_before_migration(self):
        overrides = self.production()
        result = self.build("--production", FAKE_VOLUME_EXISTS=1, **overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        order = [self.index("stack.sh stop api realtime"), self.index("backup-postgres.sh --production"),
                 self.index("stack.sh migrate")]
        self.assertEqual(order, sorted(order))
        backups = list((self.srv / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertRegex(backups[0].name, r"^hine-[0-9]{8}T[0-9]{6}Z\.dump$")

    def test_same_commit_with_new_domain_replaces_release_and_recreates_caddy(self):
        self.assertEqual(self.build("--production", **self.production()).returncode, 0)
        other = self.srv / "releases/bbbbbbbbbbbb/web"
        other.mkdir(parents=True)
        (other / "index.html").write_text("older release")
        self.log.write_text("")
        result = self.build("--production", **self.production("chat.example.org"))
        self.assertEqual(result.returncode, 0, result.stderr)
        web = self.srv / "releases/0123456789ab/web"
        self.assertIn("https://chat.example.org", (web / "index.html").read_text())
        self.assertIn("stack.sh up -d --no-deps --force-recreate --wait --wait-timeout 180 caddy", self.log.read_text())
        self.assertEqual(sorted(path.name for path in (self.srv / "releases/0123456789ab").iterdir()), ["web"])
        self.assertEqual((other / "index.html").read_text(), "older release")
        self.log.write_text("")
        self.assertEqual(self.build("--production", **self.production("chat.example.org")).returncode, 0)
        self.assertNotIn("--force-recreate", self.log.read_text())

    def test_failed_deploy_keeps_previous_active_release_and_shows_log_tail(self):
        overrides = self.production()
        self.srv.mkdir()
        previous = (f"HINE_ACTIVE_COMMIT=aaaaaaaaaaaa\nWEB_ROOT={self.srv}/releases/aaaaaaaaaaaa/web\n"
                    f"COMPOSE_PROJECT_NAME=hine-production\nHINE_SECRET_DIR={self.srv}/secrets\n"
                    "HINE_EDGE_SUBNET=172.30.1.0/24\nHINE_BACKEND_SUBNET=172.30.2.0/24\n"
                    "HINE_RUNTIME_UID=1\nHINE_RUNTIME_GID=1\nHINE_DEPLOYED_AT=20261017T000000Z\n")
        (self.srv / "active.env").write_text(previous)
        result = self.build("--production", FAKE_FAIL_OPERATION="stack.sh migrate", **overrides)
        self.assertEqual(result.returncode, 1)
        self.assertIn("記錄檔最後 30 行", result.stderr)
        self.assertIn("stub failure detail", result.stderr)
        self.assertIn("建議解法：", result.stderr)
        self.assertIn("backups", result.stderr)
        self.assertEqual((self.srv / "active.env").read_text(), previous)
        self.assertFalse((self.root / ".build.lock").exists())

    def test_production_subcommands_use_the_active_release_not_the_checkout(self):
        overrides = self.production()
        self.assertEqual(self.build("--production", **overrides).returncode, 0)
        self.log.write_text("")
        result = self.build("--production", "status", FAKE_COMMIT="ffffffffffff", **overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0123456789ab", result.stdout)
        self.assertIn(f"WEB_ROOT={self.srv}/releases/0123456789ab/web", self.calls()[self.index("stack.sh ps")])
        result = self.build("--production", "logs", "api", "--follow", **overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.index("stack.sh logs --tail 200 --follow api")

    def test_production_status_before_any_deploy_says_so(self):
        result = self.build("--production", "status", **self.production())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("尚未部署", result.stdout)
        self.assertNotEqual(self.build("--production", "stop", **self.production()).returncode, 0)


if __name__ == "__main__":
    unittest.main()
