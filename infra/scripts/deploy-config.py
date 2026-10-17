"""Strict parser for deploy.env and active.env.

The files are never executed: only allowlisted KEY=VALUE lines with shell-inert values are accepted, and validated
values are printed as KEY=VALUE lines for build.sh to export.
"""
import ipaddress
import re
import sys
from pathlib import Path

LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
SAFE = re.compile(r"^[A-Za-z0-9._@:/,+-]*$")
DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63}$")
BUCKET = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
COMMIT = re.compile(r"^[0-9a-f]{12}$")
STAMP = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
NUMBER = re.compile(r"^[0-9]+$")
DEFAULT_SUBNETS = {"HINE_EDGE_SUBNET": "172.30.1.0/24", "HINE_BACKEND_SUBNET": "172.30.2.0/24"}
DEPLOY_REQUIRED = ("HINE_DOMAIN", "ACME_EMAIL", "HINE_EXPECTED_IP")
GCS_KEYS = ("GCS_BUCKET", "GCS_CREDENTIALS_FILE", "GCS_PROJECT", "GCS_SIGNING_SERVICE_ACCOUNT")
DEPLOY_KEYS = DEPLOY_REQUIRED + tuple(DEFAULT_SUBNETS) + GCS_KEYS
ACTIVE_KEYS = ("HINE_ACTIVE_COMMIT", "WEB_ROOT", "COMPOSE_PROJECT_NAME", "HINE_SECRET_DIR", "HINE_EDGE_SUBNET",
               "HINE_BACKEND_SUBNET", "HINE_RUNTIME_UID", "HINE_RUNTIME_GID", "HINE_DEPLOYED_AT")
PRODUCTION_PROJECT = "hine-production"


class ConfigError(ValueError):
    pass


def read_pairs(path, allowed):
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            raise ConfigError(f"{path.name} 第 {number} 行：格式必須是 KEY=VALUE")
        key, value = match.groups()
        if key not in allowed:
            raise ConfigError(f"{path.name} 第 {number} 行：不允許的欄位 {key}")
        if key in values:
            raise ConfigError(f"{path.name} 第 {number} 行：欄位 {key} 重複")
        if not SAFE.match(value):
            raise ConfigError(f"{path.name} 第 {number} 行：{key} 含不允許的字元（不可有空白、引號、$ 或反引號）")
        values[key] = value
    return values


def public_ipv4_list(key, text):
    addresses = []
    for part in text.split(","):
        try:
            address = ipaddress.IPv4Address(part)
        except ValueError:
            raise ConfigError(f"{key} 必須是 IPv4 位址（多個以逗號分隔）：{part}") from None
        if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast \
                or address.is_unspecified or address.is_reserved:
            raise ConfigError(f"{key} 必須是 VM 的對外 IPv4，不可是私有或保留位址：{part}")
        addresses.append(str(address))
    return ",".join(addresses)


def private_subnet(key, text):
    try:
        network = ipaddress.IPv4Network(text, strict=True)
    except ValueError:
        raise ConfigError(f"{key} 必須是 IPv4 CIDR（例如 172.30.1.0/24）：{text}") from None
    if not network.is_private or not 16 <= network.prefixlen <= 28:
        raise ConfigError(f"{key} 必須是私有網段，前綴長度 /16 到 /28：{text}")
    return network


def subnets(values):
    edge = private_subnet("HINE_EDGE_SUBNET", values.get("HINE_EDGE_SUBNET") or DEFAULT_SUBNETS["HINE_EDGE_SUBNET"])
    backend = private_subnet("HINE_BACKEND_SUBNET",
                             values.get("HINE_BACKEND_SUBNET") or DEFAULT_SUBNETS["HINE_BACKEND_SUBNET"])
    if edge.overlaps(backend):
        raise ConfigError(f"HINE_EDGE_SUBNET {edge} 與 HINE_BACKEND_SUBNET {backend} 重疊")
    return [("HINE_EDGE_SUBNET", str(edge)), ("HINE_BACKEND_SUBNET", str(backend)),
            ("TRUSTED_PROXY_NETWORKS", f"{edge},{backend}")]


def deploy(path):
    values = read_pairs(path, DEPLOY_KEYS)
    for key in DEPLOY_REQUIRED:
        if not values.get(key):
            raise ConfigError(f"deploy.env 缺少必填欄位 {key}")
    if not DOMAIN.match(values["HINE_DOMAIN"]):
        raise ConfigError("HINE_DOMAIN 必須是網域名稱，不含 https:// 與連接埠（例如 hine.run.place）")
    if not EMAIL.match(values["ACME_EMAIL"]):
        raise ConfigError("ACME_EMAIL 必須是有效的電子郵件地址")
    pairs = [("HINE_DOMAIN", values["HINE_DOMAIN"]), ("ACME_EMAIL", values["ACME_EMAIL"]),
             ("HINE_EXPECTED_IP", public_ipv4_list("HINE_EXPECTED_IP", values["HINE_EXPECTED_IP"]))]
    pairs += subnets(values)
    checks = {"GCS_BUCKET": BUCKET, "GCS_PROJECT": PROJECT, "GCS_SIGNING_SERVICE_ACCOUNT": EMAIL}
    for key in GCS_KEYS:
        value = values.get(key, "")
        if not value:
            continue
        if key == "GCS_CREDENTIALS_FILE":
            if not value.startswith("/"):
                raise ConfigError("GCS_CREDENTIALS_FILE 必須是絕對路徑")
        elif not checks[key].match(value):
            raise ConfigError(f"{key} 格式不正確：{value}")
        pairs.append((key, value))
    return pairs


def absolute(key, value):
    if not value.startswith("/") or "/../" in value + "/" or "//" in value:
        raise ConfigError(f"active.env 的 {key} 必須是絕對路徑")
    return value


def active(path):
    values = read_pairs(path, ACTIVE_KEYS)
    missing = [key for key in ACTIVE_KEYS if not values.get(key)]
    if missing:
        raise ConfigError(f"active.env 缺少欄位 {', '.join(missing)}")
    commit = values["HINE_ACTIVE_COMMIT"]
    if not COMMIT.match(commit):
        raise ConfigError("active.env 的 HINE_ACTIVE_COMMIT 必須是 12 位小寫十六進位")
    web_root = absolute("WEB_ROOT", values["WEB_ROOT"])
    if not web_root.endswith(f"/releases/{commit}/web"):
        raise ConfigError("active.env 的 WEB_ROOT 與 HINE_ACTIVE_COMMIT 不一致")
    if values["COMPOSE_PROJECT_NAME"] != PRODUCTION_PROJECT:
        raise ConfigError(f"active.env 的 COMPOSE_PROJECT_NAME 必須是 {PRODUCTION_PROJECT}")
    for key in ("HINE_RUNTIME_UID", "HINE_RUNTIME_GID"):
        if not NUMBER.match(values[key]):
            raise ConfigError(f"active.env 的 {key} 必須是數字")
    if not STAMP.match(values["HINE_DEPLOYED_AT"]):
        raise ConfigError("active.env 的 HINE_DEPLOYED_AT 格式不正確")
    pairs = [("HINE_ACTIVE_COMMIT", commit), ("WEB_ROOT", web_root),
             ("COMPOSE_PROJECT_NAME", values["COMPOSE_PROJECT_NAME"]),
             ("HINE_SECRET_DIR", absolute("HINE_SECRET_DIR", values["HINE_SECRET_DIR"])),
             ("HINE_RUNTIME_UID", values["HINE_RUNTIME_UID"]), ("HINE_RUNTIME_GID", values["HINE_RUNTIME_GID"]),
             ("HINE_DEPLOYED_AT", values["HINE_DEPLOYED_AT"])]
    return pairs + subnets(values)


def parse(kind, path):
    if kind == "deploy":
        return deploy(path)
    if kind == "active":
        return active(path)
    raise ConfigError("用法：deploy-config.py deploy|active FILE")


def main(argv):
    if len(argv) != 2:
        print("deploy-config: 用法：deploy-config.py deploy|active FILE", file=sys.stderr)
        return 2
    try:
        pairs = parse(argv[0], Path(argv[1]))
    except (ConfigError, OSError, UnicodeDecodeError) as error:
        print(f"deploy-config: {error}", file=sys.stderr)
        return 2
    for key, value in pairs:
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
