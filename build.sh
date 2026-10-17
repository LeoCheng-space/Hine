#!/bin/sh
# HINE 一鍵安裝／部署入口。操作手冊：docs/deployment/one-click.md
set -eu
umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPTS="$ROOT/infra/scripts"
LOCAL_PORT=8443
LOCAL_URL=https://localhost:8443
PRODUCTION_PROJECT=hine-production
PRODUCTION_HOME=${HINE_PRODUCTION_HOME:-/srv/hine}
OS_RELEASE=${HINE_OS_RELEASE:-/etc/os-release}
BUN_VERSION=1.4.2
BUN_SHA256_X64=36368faef7527875d5ffa52e53cd48021741f2a83eb6208a8dd64068d422a913
BUN_SHA256_AARCH64=54328bbc2d9c8e0c9f892c544d66c57a83b84139e34909e5ee81758f1ac8fda7
MIN_COMPOSE_MAJOR=2
MIN_COMPOSE_MINOR=20
LOCK_DIR="$ROOT/.build.lock"

# Inherited Compose/product settings must never redirect either mode.
unset COMPOSE_FILE COMPOSE_PROFILES COMPOSE_PROJECT_NAME HINE_ENV HINE_SECRET_DIR WEB_ROOT HINE_DOMAIN ACME_EMAIL \
    TRUSTED_PROXY_NETWORKS PUBLIC_ORIGIN HINE_EXPECTED_IP HINE_EDGE_SUBNET HINE_BACKEND_SUBNET HINE_RUNTIME_UID \
    HINE_RUNTIME_GID GCS_BUCKET GCS_CREDENTIALS_FILE GCS_PROJECT GCS_SIGNING_SERVICE_ACCOUNT

usage() {
    cat <<'EOF'
用法：./build.sh [--production] [stop | status | logs [服務] [--follow]]
      ./build.sh clean [--yes]

  ./build.sh                 本機：安裝前置工具、建置並啟動，完成後開啟 https://localhost:8443
  ./build.sh stop            停止服務（保留資料）
  ./build.sh status          顯示服務狀態與網址
  ./build.sh logs [服務]     顯示最後 200 行記錄；加 --follow 持續顯示
  ./build.sh clean           列出本機會被清除的資料庫、Docker 容器／資料卷／映像與產生的檔案（不刪除）
  ./build.sh clean --yes     實際清除上述項目（無法復原；只限本機）
  加上 --production          改為正式機（GCP VM）模式，設定讀取 deploy.env

服務名稱：api、realtime、postgres、redis、caddy
詳細說明：docs/deployment/one-click.md
EOF
}
die() { printf 'build.sh：%s\n' "$*" >&2; exit 1; }
usage_error() { printf 'build.sh：%s\n\n' "$1" >&2; usage >&2; exit 2; }

MODE=local
COMMAND=up
SERVICE=
FOLLOW=0
YES=0
for argument in "$@"; do
    case "$argument" in
        --production) MODE=production ;;
        --help|-h) usage; exit 0 ;;
        --follow) FOLLOW=1 ;;
        --yes) YES=1 ;;
        stop|status|logs|clean)
            [ "$COMMAND" = up ] || usage_error '一次只能指定一個指令'
            COMMAND=$argument ;;
        api|realtime|postgres|redis|caddy)
            [ -z "$SERVICE" ] || usage_error '一次只能指定一個服務'
            SERVICE=$argument ;;
        *) usage_error "不支援的參數：$argument" ;;
    esac
done
if [ "$COMMAND" != logs ] && { [ -n "$SERVICE" ] || [ "$FOLLOW" = 1 ]; }; then
    usage_error '服務名稱與 --follow 只能搭配 logs 使用'
fi
[ "$YES" = 0 ] || [ "$COMMAND" = clean ] || usage_error '--yes 只能搭配 clean 使用'
[ "$MODE:$COMMAND" != production:clean ] || usage_error '正式機不提供 clean：正式機的資料不能用這個指令刪除'

# --- Output and logging --------------------------------------------------------------------
LOG_FILE=${HINE_BUILD_LOG:-}
STEP_TOTAL=0
LOCK_HELD=0
STAGING=
start_log() {
    [ -z "$LOG_FILE" ] || return 0
    mkdir -p "$ROOT/.build-logs"
    chmod 700 "$ROOT/.build-logs"
    LOG_FILE="$ROOT/.build-logs/$(date -u +%Y%m%dT%H%M%SZ)-$MODE.log"
    : > "$LOG_FILE"
    chmod 600 "$LOG_FILE"
}
STEP_HINT=
# step NUMBER TITLE HINT: the hint is printed with the log tail if anything in this step fails.
step() {
    STEP_HINT=${3:-}
    printf '[%s/%s] %s\n' "$1" "$STEP_TOTAL" "$2"
    printf '\n== [%s/%s] %s\n' "$1" "$STEP_TOTAL" "$2" >> "$LOG_FILE"
}
fail_with_log() {
    printf 'build.sh：%s\n' "$1" >&2
    if [ -n "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        printf -- '--- 記錄檔最後 30 行 ---\n' >&2
        tail -n 30 "$LOG_FILE" >&2
        printf -- '--- 完整記錄：%s\n' "$LOG_FILE" >&2
    fi
    [ -z "$STEP_HINT" ] || printf '\n建議解法：%s\n' "$STEP_HINT" >&2
    printf '更多疑難排解：docs/deployment/one-click.md 第 4 節\n' >&2
    exit 1
}
run() {
    printf '+ %s\n' "$*" >> "$LOG_FILE"
    "$@" >> "$LOG_FILE" 2>&1 || fail_with_log "執行失敗：$*"
}
cleanup() {
    [ -z "$STAGING" ] || rm -rf "$STAGING"
    [ "$LOCK_HELD" = 0 ] || rm -rf "$LOCK_DIR"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

# --- Prerequisites -------------------------------------------------------------------------
os_field() { sed -n "s/^$1=//p" "$OS_RELEASE" 2>/dev/null | head -n 1 | tr -d '"'; }
debian_family() {
    case " $(os_field ID) $(os_field ID_LIKE) " in *" debian "*|*" ubuntu "*) return 0 ;; esac
    return 1
}
manual_install_help() {
    cat >&2 <<'EOF'
build.sh：自動安裝只支援 Ubuntu／Debian。請先手動安裝以下工具後再執行：
  - Docker Engine 與 Compose v2.20 以上：https://docs.docker.com/engine/install/
  - git、curl、python3、openssl、unzip、iproute2（ss 指令）
  - Bun 會由 build.sh 自動下載並以校驗碼驗證，不需手動安裝
EOF
    exit 1
}
compose_version_ok() {
    version=$(docker compose version --short 2>/dev/null) || return 1
    version=${version#v}
    major=${version%%.*}
    rest=${version#*.}
    minor=${rest%%.*}
    case "$major" in ""|*[!0-9]*) return 1 ;; esac
    case "$minor" in ""|*[!0-9]*) return 1 ;; esac
    [ "$major" -gt "$MIN_COMPOSE_MAJOR" ] || { [ "$major" -eq "$MIN_COMPOSE_MAJOR" ] && [ "$minor" -ge "$MIN_COMPOSE_MINOR" ]; }
}
install_docker() {
    distro=$(os_field ID)
    codename=$(os_field VERSION_CODENAME)
    case "$distro" in ubuntu|debian) ;; *) manual_install_help ;; esac
    case "$codename" in ""|*[!a-z0-9]*) die '無法從 /etc/os-release 取得版本代號，請依 https://docs.docker.com/engine/install/ 手動安裝 Docker' ;; esac
    architecture=$(dpkg --print-architecture)
    case "$architecture" in ""|*[!a-z0-9]*) die '無法判斷套件架構' ;; esac
    run sudo install -m 0755 -d /etc/apt/keyrings
    run sudo curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc
    run sudo chmod a+r /etc/apt/keyrings/docker.asc
    source_list=$(mktemp)
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "$architecture" "$distro" "$codename" > "$source_list"
    run sudo install -m 0644 "$source_list" /etc/apt/sources.list.d/docker.list
    rm -f "$source_list"
    run sudo apt-get update
    run sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    if [ -d /run/systemd/system ]; then run sudo systemctl enable --now docker; fi
}
BUN=
ensure_bun() {
    for candidate in "$(command -v bun 2>/dev/null || true)" "$HOME/.bun/bin/bun" "$HOME/.local/share/hine/bun-$BUN_VERSION/bun"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        if [ "$("$candidate" --version 2>/dev/null || true)" = "$BUN_VERSION" ]; then
            BUN=$candidate
            return 0
        fi
    done
    [ "$(uname -s)" = Linux ] || die "自動安裝 Bun 只支援 Linux；請手動安裝 Bun $BUN_VERSION"
    case "$(uname -m)" in
        x86_64|amd64) asset=bun-linux-x64; expected=$BUN_SHA256_X64 ;;
        aarch64|arm64) asset=bun-linux-aarch64; expected=$BUN_SHA256_AARCH64 ;;
        *) die "不支援的處理器架構 $(uname -m)；請手動安裝 Bun $BUN_VERSION" ;;
    esac
    workspace=$(mktemp -d)
    run curl -fsSL -o "$workspace/$asset.zip" "https://github.com/oven-sh/bun/releases/download/bun-v$BUN_VERSION/$asset.zip"
    actual=$(sha256sum "$workspace/$asset.zip" | cut -d ' ' -f 1)
    if [ "$actual" != "$expected" ]; then
        rm -rf "$workspace"
        die "Bun 下載檔的 SHA-256 不符（預期 $expected，實際 $actual），已停止安裝"
    fi
    run unzip -q "$workspace/$asset.zip" -d "$workspace"
    destination="$HOME/.local/share/hine/bun-$BUN_VERSION"
    mkdir -p "$destination"
    install -m 755 "$workspace/$asset/bun" "$destination/bun"
    rm -rf "$workspace"
    BUN="$destination/bun"
    [ "$("$BUN" --version)" = "$BUN_VERSION" ] || die "安裝後的 Bun 版本不是 $BUN_VERSION"
}
install_prerequisites() {
    missing=
    for tool in git curl python3 openssl unzip sha256sum ss; do
        command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
    done
    need_docker=0
    { command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; } || need_docker=1
    if [ -n "$missing" ] || [ "$need_docker" = 1 ]; then
        debian_family || manual_install_help
        command -v sudo >/dev/null 2>&1 || die '需要 sudo 才能自動安裝缺少的工具'
        [ "$need_docker" = 0 ] || missing="$missing docker"
        printf '  需要安裝：%s（可能會要求輸入 sudo 密碼）\n' "$missing"
        run sudo apt-get update
        run sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git gnupg iproute2 \
            openssl python3 unzip
        [ "$need_docker" = 0 ] || install_docker
    fi
    compose_version_ok || die "需要 Docker Compose v$MIN_COMPOSE_MAJOR.$MIN_COMPOSE_MINOR 以上（目前：$(docker compose version --short 2>/dev/null || printf '無')）；請更新 Docker 後再執行"
    ensure_bun
}
shell_quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
# Re-runs this script with the docker group active for the current login (e.g. right after usermod, before re-login).
# Every argument already passed the allowlist above; only paths need quoting. sg makes docker the primary group, so
# switch straight back to the user's own primary group: files keep their normal owner group (existing .secrets stay
# valid) and docker remains a supplementary group.
reexec_in_docker_group() {
    user=$(id -un)
    command -v sg >/dev/null 2>&1 || die '找不到 sg 指令；請登出再登入讓 docker 群組生效後重新執行'
    primary_group=$(id -gn "$user")
    case "$primary_group" in ""|*[!A-Za-z0-9._-]*) die "無法判斷使用者 $user 的主要群組；請登出再登入後重新執行" ;; esac
    inner=HINE_BUILD_REEXEC=1
    [ -z "$LOG_FILE" ] || inner="$inner HINE_BUILD_LOG=$(shell_quote "$LOG_FILE")"
    inner="$inner sh $(shell_quote "$ROOT/build.sh")"
    for argument in "$@"; do inner="$inner $argument"; done
    command_line="sg $primary_group -c $(shell_quote "$inner")"
    [ -z "$LOG_FILE" ] || printf '+ sg docker -c %s\n' "$command_line" >> "$LOG_FILE"
    exec sg docker -c "$command_line"
}
# Install/deploy: may add the user to the docker group first. Runs before the lock exists; the re-executed process
# takes the lock itself.
ensure_docker_access() {
    docker info >/dev/null 2>&1 && return 0
    [ "${HINE_BUILD_REEXEC:-}" != 1 ] || die '已切換到 docker 群組但仍無法連線 Docker；請確認 Docker 服務正在執行（sudo systemctl status docker）'
    if ! id -nG "$(id -un)" | tr ' ' '\n' | grep -qx docker; then
        command -v sudo >/dev/null 2>&1 || die "使用者 $(id -un) 不在 docker 群組，且沒有 sudo 可以加入"
        run sudo usermod -aG docker "$(id -un)"
    fi
    printf '  以 docker 群組重新執行（本次不需登出）\n'
    reexec_in_docker_group "$@"
}
# stop/status/logs: never change group membership, but use the docker group the user already has.
require_docker_session() {
    command -v docker >/dev/null 2>&1 || die '尚未安裝 Docker；請先執行 ./build.sh'
    docker info >/dev/null 2>&1 && return 0
    [ "${HINE_BUILD_REEXEC:-}" != 1 ] || die '已切換到 docker 群組但仍無法連線 Docker；請確認 Docker 服務正在執行（sudo systemctl status docker）'
    id -nG "$(id -un)" | tr ' ' '\n' | grep -qx docker \
        || die "使用者 $(id -un) 還不在 docker 群組；請先執行 ./build.sh（會自動加入並啟動服務）"
    reexec_in_docker_group "$@"
}
acquire_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        holder=$(cat "$LOCK_DIR/pid" 2>/dev/null || printf '未知')
        die "已有另一個 build.sh 在執行（PID $holder）。若確定沒有在執行，請刪除 $LOCK_DIR 後重試"
    fi
    LOCK_HELD=1
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
}

# --- Port ownership ------------------------------------------------------------------------
# A port held by this deployment's own Caddy is a rerun, anything else stops before starting.
check_port() {
    port=$1
    project=$2
    owners=$(docker ps --filter "publish=$port" \
        --format '{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Label "com.docker.compose.service"}}') \
        || die '無法查詢 Docker 容器'
    if [ -n "$owners" ]; then
        conflict=$(printf '%s\n' "$owners" | awk -F'|' -v project="$project" \
            '!($2 == project && $3 == "caddy") { print $1 "（專案 " ($2 == "" ? "無" : $2) "）"; exit }')
        [ -z "$conflict" ] || die "連接埠 $port 已被容器 ${conflict}占用；請先停止它（docker stop 容器名稱）再執行"
        return 0
    fi
    if ss -Hltn "( sport = :$port )" | grep -q .; then
        die "連接埠 $port 已被其他程式占用（不是 Docker 容器）；可用 sudo ss -ltnp 'sport = :$port' 查看是哪個程式"
    fi
}

build_frontend() {
    run sh -c 'cd "$1" && "$2" install --frozen-lockfile' sh "$ROOT/frontend/app" "$BUN"
    run env PUBLIC_ORIGIN="$1" sh -c 'cd "$1" && "$2" run build' sh "$ROOT/frontend/app" "$BUN"
}

# --- Local mode ----------------------------------------------------------------------------
# Before the first install (or after clean) there is no .env yet; Compose then reads the example instead.
LOCAL_ENV_FILE="$ROOT/.env"
# The project name must come from the same file Compose is given, or this script would act on a different project.
local_project() {
    name=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' "$LOCAL_ENV_FILE" 2>/dev/null | tail -n 1)
    case "$name" in "") name=hine-dev ;; *[!a-z0-9_-]*) die "$(basename "$LOCAL_ENV_FILE") 的 COMPOSE_PROJECT_NAME 格式不正確" ;; esac
    printf '%s' "$name"
}
compose_local() {
    docker compose --project-directory "$ROOT" --env-file "$LOCAL_ENV_FILE" \
        -f "$ROOT/docker-compose.yml" -f "$ROOT/infra/docker/compose.local.yml" \
        --profile product --profile realtime --profile local "$@"
}
local_up() {
    STEP_TOTAL=5
    step 1 '檢查並安裝前置工具' '確認網路能連到 download.docker.com 與 github.com、這個帳號可以使用 sudo；從上面記錄找出失敗的套件或下載後重跑 ./build.sh'
    install_prerequisites
    ensure_docker_access "$@"
    acquire_lock
    step 2 '產生密鑰與設定（已存在就沿用）' '多半是 .secrets/ 或 .env 的擁有者與目前使用者不同（用 ls -ln .secrets .env 檢查），或密鑰檔被改過。若不需要舊資料：執行 ./build.sh clean 預覽、./build.sh clean --yes 清除後，再重跑 ./build.sh'
    run sh "$SCRIPTS/init-dev.sh"
    step 3 '建置前端' '前端套件下載或建置失敗：確認網路能連到 registry.npmjs.org 後重跑 ./build.sh；仍失敗請把完整記錄檔提供給維護者'
    build_frontend "$LOCAL_URL"
    step 4 '啟動服務並等待健康檢查' '用 ./build.sh status 找出沒有變成 healthy 的服務，再用 ./build.sh logs 服務名稱 看原因；資料庫密碼不符、映像下載失敗、連接埠衝突的處理見手冊第 4 節'
    check_port "$LOCAL_PORT" "$(local_project)"
    run compose_local up -d --build --wait --wait-timeout 180
    step 5 '完成'
    printf '\nHINE 已啟動：%s\n' "$LOCAL_URL"
    printf '第一次開啟時瀏覽器會顯示憑證警告，請按「進階」→「繼續前往 localhost」。\n'
    printf '停止：./build.sh stop　狀態：./build.sh status　記錄：./build.sh logs\n'
}
local_command() {
    [ -f "$ROOT/.env" ] || die '尚未建置；請先執行 ./build.sh'
    case "$COMMAND" in
        stop) compose_local stop ;;
        status) compose_local ps; printf '網址：%s\n' "$LOCAL_URL" ;;
        logs)
            set -- --tail 200
            [ "$FOLLOW" = 0 ] || set -- "$@" --follow
            [ -z "$SERVICE" ] || set -- "$@" "$SERVICE"
            compose_local logs "$@" ;;
    esac
}

CLEAN_FILES=".env .secrets .build-logs frontend/app/dist frontend/app/node_modules"
show_items() {
    printf '  %s：\n' "$1"
    if [ -n "$2" ]; then printf '%s\n' "$2" | sed 's/^/    - /'; else printf '    （無）\n'; fi
}
# Deletes only this checkout's Compose project (containers, networks, every volume, images it built) and the files
# build.sh generates. Pulled base images and the build cache are shared machine-wide and stay; deploy.env stays.
# Compose project names are machine-wide and every checkout defaults to hine-dev, so the project must provably belong
# to this directory before anything is listed for deletion.
local_clean() {
    [ -f "$ROOT/.env" ] || LOCAL_ENV_FILE="$ROOT/.env.example"
    project=$(local_project)
    owners=$(docker ps -a --filter "label=com.docker.compose.project=$project" \
        --format '{{.Label "com.docker.compose.project.working_dir"}}') || die '無法查詢 Docker 容器，未清除任何東西'
    owners=$(printf '%s\n' "$owners" | sort -u)
    foreign=$(printf '%s\n' "$owners" | grep -vx -F -e "$ROOT" -e '' || true)
    [ -z "$foreign" ] || die "Docker 專案 $project 的容器是從另一個資料夾建立的：$foreign
為了不刪到那邊的資料，這裡不會清除。請到那個資料夾執行 ./build.sh clean，或在這份 .env 改用不同的 COMPOSE_PROJECT_NAME"
    volumes=$(docker volume ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}')
    if [ ! -f "$ROOT/.env" ] && [ -z "$owners" ] && [ -n "$volumes" ]; then
        die "找到 Docker 專案 $project 的資料卷，但這個資料夾沒有 .env、也沒有容器可以對照，無法確認資料屬於這裡，因此不會清除。
確定這些資料卷要刪除，請手動執行：docker volume rm $(printf '%s' "$volumes" | tr '\n' ' ')"
    fi
    containers=$(compose_local ps -a --format '{{.Name}}' 2>/dev/null || true)
    networks=$(docker network ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}')
    images=$(docker image ls --filter "label=com.docker.compose.project=$project" --format '{{.Repository}}:{{.Tag}}')
    files=
    for path in $CLEAN_FILES; do
        if [ -e "$ROOT/$path" ] || [ -L "$ROOT/$path" ]; then files="$files$path
"; fi
    done
    printf '本機 Docker 專案 %s 將被清除：\n' "$project"
    show_items '容器' "$containers"
    show_items '資料卷（資料庫、Redis、本機憑證）' "$volumes"
    show_items '網路' "$networks"
    show_items '本專案建置的映像' "$images"
    show_items '產生的檔案' "${files%
}"
    printf '  保留：deploy.env、共用的基礎映像（postgres／redis／caddy）與 Docker 建置快取\n'
    if [ "$YES" = 0 ]; then
        printf '\n這只是預覽，沒有刪除任何東西。確定要刪除（無法復原）請執行：./build.sh clean --yes\n'
        return 0
    fi
    printf '\n開始清除…\n'
    compose_local down -v --remove-orphans --rmi local || die "Docker 專案 $project 清除失敗；請確認 Docker 正常後重新執行 ./build.sh clean --yes"
    for path in $CLEAN_FILES; do rm -rf "${ROOT:?}/$path"; done
    printf '\n已清除。重新安裝請執行：./build.sh\n'
}

# --- Production mode -----------------------------------------------------------------------
load_config() {
    output=$(python3 "$SCRIPTS/deploy-config.py" "$1" "$2" 2>&1) || die "${output#deploy-config: }"
    while IFS='=' read -r key value; do
        case "$key" in
            HINE_DOMAIN|ACME_EMAIL|HINE_EXPECTED_IP|HINE_EDGE_SUBNET|HINE_BACKEND_SUBNET|TRUSTED_PROXY_NETWORKS|\
            GCS_BUCKET|GCS_CREDENTIALS_FILE|GCS_PROJECT|GCS_SIGNING_SERVICE_ACCOUNT|HINE_ACTIVE_COMMIT|WEB_ROOT|\
            COMPOSE_PROJECT_NAME|HINE_SECRET_DIR|HINE_RUNTIME_UID|HINE_RUNTIME_GID|HINE_DEPLOYED_AT)
                export "$key=$value" ;;
            "") ;;
            *) die "設定解析器輸出了未預期的欄位：$key" ;;
        esac
    done <<EOF
$output
EOF
}
load_deploy_env() {
    file="$ROOT/deploy.env"
    [ ! -L "$file" ] || die 'deploy.env 不可以是符號連結'
    if [ ! -e "$file" ]; then
        (set -C; cat "$ROOT/deploy.env.example" > "$file") || die '無法建立 deploy.env'
        chmod 600 "$file"
        die "已建立 deploy.env 範本：$file
請填入 HINE_DOMAIN、ACME_EMAIL、HINE_EXPECTED_IP（GCS 欄位可留空），完成後重新執行 ./build.sh --production"
    fi
    [ -f "$file" ] || die 'deploy.env 必須是一般檔案'
    load_config deploy "$file"
}
production_prechecks() {
    check_port 80 "$PRODUCTION_PROJECT"
    check_port 443 "$PRODUCTION_PROJECT"
    answers=$(getent ahosts "$HINE_DOMAIN" 2>/dev/null || true)
    printf '%s\n' "$answers" >> "$LOG_FILE"
    message=$(printf '%s\n' "$answers" | python3 "$SCRIPTS/deploy-checks.py" dns "$HINE_EXPECTED_IP" 2>&1) \
        || die "DNS 預檢未通過：$message。請先把 $HINE_DOMAIN 的 A 紀錄指向 $HINE_EXPECTED_IP 並移除 AAAA 紀錄；DNS 生效前不會申請憑證"
    inspected=$(mktemp)
    ids=$(docker network ls -q)
    if [ -n "$ids" ]; then
        # Network IDs are hexadecimal; word splitting is intended.
        # shellcheck disable=SC2086
        docker network inspect $ids > "$inspected"
    else
        printf '[]' > "$inspected"
    fi
    message=$(python3 "$SCRIPTS/deploy-checks.py" subnets "$PRODUCTION_PROJECT" "$HINE_EDGE_SUBNET" \
        "$HINE_BACKEND_SUBNET" < "$inspected" 2>&1) || { rm -f "$inspected"; die "子網路檢查未通過：
$message"; }
    rm -f "$inspected"
}
prepare_production_home() {
    case "$PRODUCTION_HOME" in /*) ;; *) die 'HINE_PRODUCTION_HOME 必須是絕對路徑' ;; esac
    HINE_RUNTIME_UID=$(id -u)
    HINE_RUNTIME_GID=$(id -g)
    export HINE_RUNTIME_UID HINE_RUNTIME_GID
    # Static releases must stay traversable for Caddy; credentials and backups stay private.
    run sudo install -d -m 755 -o "$HINE_RUNTIME_UID" -g "$HINE_RUNTIME_GID" "$PRODUCTION_HOME" "$PRODUCTION_HOME/releases"
    run sudo install -d -m 700 -o "$HINE_RUNTIME_UID" -g "$HINE_RUNTIME_GID" "$PRODUCTION_HOME/secrets" "$PRODUCTION_HOME/backups"
}
prepare_production_secrets() {
    configuration="$ROOT/.env"
    [ -f "$configuration" ] || configuration="$ROOT/.env.example"
    targets=$(python3 "$SCRIPTS/database-reference.py" "$configuration") || die '.env 的資料庫設定不正確或不明確'
    run sh "$SCRIPTS/init-secrets.sh" "$PRODUCTION_HOME/secrets" "${targets%% *}" "${targets#* }"
    run sh "$SCRIPTS/init-env.sh" "$HINE_RUNTIME_UID" "$HINE_RUNTIME_GID"
}
RELEASE_COMMIT=
REPLACED_WEB=0
PREVIOUS_WEB=
publish_frontend() {
    RELEASE_COMMIT=$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null) || die '無法取得目前的 git commit；請用 git clone 取得程式碼'
    case "$RELEASE_COMMIT" in *[!0-9a-f]*|"") die "git commit 格式不正確：$RELEASE_COMMIT" ;; esac
    build_frontend "https://$HINE_DOMAIN"
    release="$PRODUCTION_HOME/releases/$RELEASE_COMMIT"
    target="$release/web"
    mkdir -p "$release"
    chmod 755 "$release"
    STAGING="$release/web.new-$$"
    rm -rf "$STAGING"
    cp -R "$ROOT/frontend/app/dist" "$STAGING"
    find "$STAGING" -type d -exec chmod 755 {} +
    find "$STAGING" -type f -exec chmod 644 {} +
    if [ ! -e "$target" ]; then
        mv "$STAGING" "$target"
    elif diff -r "$target" "$STAGING" >/dev/null 2>&1; then
        rm -rf "$STAGING"
    else
        # Same commit, different build (e.g. new HINE_DOMAIN): replace it and recreate Caddy later.
        PREVIOUS_WEB="$release/web.prev-$(date -u +%Y%m%dT%H%M%SZ)"
        mv "$target" "$PREVIOUS_WEB"
        mv "$STAGING" "$target"
        REPLACED_WEB=1
    fi
    STAGING=
    WEB_ROOT=$target
    export WEB_ROOT
}
export_production_env() {
    HINE_ENV=production
    COMPOSE_PROJECT_NAME=$PRODUCTION_PROJECT
    HINE_SECRET_DIR="$PRODUCTION_HOME/secrets"
    TRUSTED_PROXY_NETWORKS="$HINE_EDGE_SUBNET,$HINE_BACKEND_SUBNET"
    export HINE_ENV COMPOSE_PROJECT_NAME HINE_SECRET_DIR TRUSTED_PROXY_NETWORKS HINE_EDGE_SUBNET HINE_BACKEND_SUBNET \
        HINE_DOMAIN ACME_EMAIL HINE_EXPECTED_IP WEB_ROOT HINE_RUNTIME_UID HINE_RUNTIME_GID
}
start_production() {
    run sh "$SCRIPTS/preflight.sh" --local
    if docker volume inspect "${PRODUCTION_PROJECT}_postgres_data" >/dev/null 2>&1; then
        printf '  偵測到既有資料：先停止寫入並備份資料庫\n'
        run sh "$SCRIPTS/stack.sh" stop api realtime
        run sh "$SCRIPTS/stack.sh" up -d --wait --wait-timeout 120 postgres redis
        run sh "$SCRIPTS/backup-postgres.sh" --production "$PRODUCTION_HOME/backups/hine-$(date -u +%Y%m%dT%H%M%SZ).dump"
    fi
    run sh "$SCRIPTS/stack.sh" up -d --wait --wait-timeout 120 postgres redis
    run sh "$SCRIPTS/stack.sh" migrate
    run sh "$SCRIPTS/stack.sh" up -d --build --wait --wait-timeout 180
    if [ "$REPLACED_WEB" = 1 ]; then
        run sh "$SCRIPTS/stack.sh" up -d --no-deps --force-recreate --wait --wait-timeout 180 caddy
    fi
    run sh "$SCRIPTS/preflight.sh" --public
}
write_active_env() {
    temporary="$PRODUCTION_HOME/.active.env.$$"
    {
        printf 'HINE_ACTIVE_COMMIT=%s\n' "$RELEASE_COMMIT"
        printf 'WEB_ROOT=%s\n' "$WEB_ROOT"
        printf 'COMPOSE_PROJECT_NAME=%s\n' "$PRODUCTION_PROJECT"
        printf 'HINE_SECRET_DIR=%s\n' "$HINE_SECRET_DIR"
        printf 'HINE_EDGE_SUBNET=%s\n' "$HINE_EDGE_SUBNET"
        printf 'HINE_BACKEND_SUBNET=%s\n' "$HINE_BACKEND_SUBNET"
        printf 'HINE_RUNTIME_UID=%s\n' "$HINE_RUNTIME_UID"
        printf 'HINE_RUNTIME_GID=%s\n' "$HINE_RUNTIME_GID"
        printf 'HINE_DEPLOYED_AT=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)"
    } > "$temporary"
    python3 "$SCRIPTS/deploy-config.py" active "$temporary" >/dev/null 2>&1 || { rm -f "$temporary"; die 'active.env 內容驗證失敗'; }
    mv -f "$temporary" "$PRODUCTION_HOME/active.env"
}
production_up() {
    STEP_TOTAL=8
    step 1 '檢查並安裝前置工具' '確認網路能連到 download.docker.com 與 github.com、這個帳號可以使用 sudo；從上面記錄找出失敗的套件或下載後重跑 ./build.sh --production'
    install_prerequisites
    ensure_docker_access "$@"
    acquire_lock
    step 2 '讀取 deploy.env'
    load_deploy_env
    step 3 '部署前檢查（連接埠、DNS、子網路）'
    production_prechecks
    step 4 "建立 $PRODUCTION_HOME 目錄" "需要 sudo 權限建立 $PRODUCTION_HOME；確認可以執行 sudo 後重跑"
    prepare_production_home
    step 5 '產生正式機密鑰（已存在就沿用）' "多半是 $PRODUCTION_HOME/secrets 的擁有者與目前使用者不同，或密鑰檔被改過；正式機密鑰不可隨意刪除重建（資料庫是用它們初始化的），請先比對 ls -ln $PRODUCTION_HOME/secrets"
    prepare_production_secrets
    step 6 '建置並發布前端' "前端建置或發布失敗：確認網路能連到 registry.npmjs.org，且 $PRODUCTION_HOME/releases 可寫入，然後重跑"
    publish_frontend
    step 7 '啟動服務（升級時先備份資料庫）' "從記錄找出是 preflight、migrate、啟動或公開探測失敗；用 ./build.sh --production status 與 logs 查看。上線版本不會改變（active.env 只在成功後更新），升級前的資料庫備份在 $PRODUCTION_HOME/backups/"
    export_production_env
    start_production
    step 8 '記錄目前版本'
    write_active_env
    [ -z "$PREVIOUS_WEB" ] || rm -rf "$PREVIOUS_WEB"
    printf '\nHINE 已部署：https://%s（版本 %s）\n' "$HINE_DOMAIN" "$RELEASE_COMMIT"
    printf '狀態：./build.sh --production status　記錄：./build.sh --production logs\n'
}
production_command() {
    active="$PRODUCTION_HOME/active.env"
    if [ ! -f "$active" ]; then
        if [ "$COMMAND" = status ]; then
            printf '正式機尚未部署（找不到 %s）。請執行 ./build.sh --production\n' "$active"
            exit 0
        fi
        die "正式機尚未部署（找不到 $active），無法執行 $COMMAND"
    fi
    load_deploy_env
    load_config active "$active"
    export_production_env
    case "$COMMAND" in
        stop) sh "$SCRIPTS/stack.sh" stop ;;
        status)
            sh "$SCRIPTS/stack.sh" ps
            printf '網址：https://%s\n目前版本：%s（%s 部署）\nWEB_ROOT：%s\n' "$HINE_DOMAIN" "$HINE_ACTIVE_COMMIT" \
                "$HINE_DEPLOYED_AT" "$WEB_ROOT" ;;
        logs)
            set -- --tail 200
            [ "$FOLLOW" = 0 ] || set -- "$@" --follow
            [ -z "$SERVICE" ] || set -- "$@" "$SERVICE"
            sh "$SCRIPTS/stack.sh" logs "$@" ;;
    esac
}

case "$MODE:$COMMAND" in
    local:up) start_log; local_up "$@" ;;
    production:up) start_log; production_up "$@" ;;
    local:clean)
        require_docker_session "$@"
        acquire_lock
        local_clean ;;
    local:*)
        require_docker_session "$@"
        [ "$COMMAND" != stop ] || acquire_lock
        local_command ;;
    production:*)
        require_docker_session "$@"
        [ "$COMMAND" != stop ] || acquire_lock
        production_command ;;
esac
