"""Owned production-Web browser acceptance over fresh native product services.

Evidence is local real-product browser coverage, not physical Android, cloud, or
formal performance acceptance. Service authority is the unchanged Components
lifecycle from tests/faults/product_fault_drill.py.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import ssl
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from playwright.async_api import Error as PlaywrightError

ROOT = Path(__file__).resolve().parents[2]
FAULTS = ROOT / "tests/faults/product_fault_drill.py"
LIMITS = [
    "NO_PHYSICAL_ANDROID_KEYBOARD_ROTATION_OR_BACKGROUND_ACCEPTANCE",
    "NO_GCS_CLOUD_BUCKET_IAM_SIGNING_OR_CORS_ACCEPTANCE",
    "NO_FORMAL_VM_MULTIUSER_PERFORMANCE_OR_50_USER_600_SECOND_RESULT",
    "PRIVATE_CADDY_LOCAL_TLS_CA_NOT_PUBLIC_CERTIFICATE_OR_OPERATOR_VM_PROOF",
]


class PrerequisiteFailure(Exception):
    pass


class AcceptanceFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _failure_sites(error: BaseException) -> list[dict]:
    sites = []
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == __file__:
            sites.append({"function": trace.tb_frame.f_code.co_name, "line": trace.tb_lineno})
        trace = trace.tb_next
    return sites


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def check(record: dict, name: str, condition: bool) -> None:
    record["checks"][name] = bool(condition)
    if not condition:
        raise AcceptanceFailure(name.upper())


def metadata_version(name: str) -> str:
    try:
        value = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        raise PrerequisiteFailure("REQUIRED_PYTHON_PACKAGE_MISSING") from None
    if not re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", value):
        raise PrerequisiteFailure("PYTHON_PACKAGE_VERSION_INVALID")
    return value


def reserve_ports(count: int) -> tuple[list[int], list[socket.socket]]:
    listeners: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return [listener.getsockname()[1] for listener in listeners], listeners
    except BaseException:
        for listener in listeners:
            listener.close()
        raise


async def build_web(bun: str, destination: Path, origin: str, private: Path) -> None:
    (private / "build-home").mkdir(mode=0o700)
    process = await asyncio.create_subprocess_exec(
        bun, "run", str(ROOT / "tests/browser/native-acceptance.ts"),
        str(destination), origin, cwd=ROOT,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "HOME": str(private / "build-home")},
    )
    try:
        output, error = await process.communicate()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        raise
    # Compiler diagnostics may include local paths; keep them private and never
    # include them in stdout, output JSON, or exception text.
    (private / "browser-build.stdout").write_bytes(output)
    (private / "browser-build.stderr").write_bytes(error)
    if process.returncode != 0 or not (destination / "index.html").is_file():
        raise AcceptanceFailure("PRODUCTION_WEB_BUILD_FAILED")


async def web_build_provenance(bun: str, destination: Path) -> tuple[str, dict[str, str], dict[str, str], str]:
    app = ROOT / "frontend/app"
    inputs = [app / "build.ts", app / "index.html", app / "package.json",
              app / "bun.lock", app / "tsconfig.json"]
    inputs.extend(path for path in (app / "src").rglob("*")
                  if path.is_file() and path.suffix in {".ts", ".tsx", ".css", ".html"})
    source_hashes = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(inputs))
    }
    process = await asyncio.create_subprocess_exec(
        bun, "--version", stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    version_output, _ = await process.communicate()
    version = version_output.decode("ascii", errors="ignore").strip()
    if process.returncode != 0 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise PrerequisiteFailure("BUN_VERSION_UNAVAILABLE")
    executable_hash = hashlib.sha256(Path(bun).resolve(strict=True).read_bytes()).hexdigest()
    asset_hashes = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob("*")) if path.is_file()
    }
    if not asset_hashes or "index.html" not in asset_hashes:
        raise AcceptanceFailure("PRODUCTION_WEB_ASSET_PROVENANCE_MISSING")
    return version, source_hashes, asset_hashes, executable_hash


async def _native_recipient(playwright, args, components, private):
    executable = args.browser_executable or {
        "chrome": "/opt/google/chrome/chrome",
        "msedge": "/opt/microsoft/msedge/msedge",
        "chromium": playwright.chromium.executable_path,
    }[args.browser]
    if not valid_exec(executable):
        raise PrerequisiteFailure("REQUESTED_NATIVE_BROWSER_UNAVAILABLE")
    profile = private / "native-recipient-profile"
    profile.mkdir(mode=0o700)
    child = await components.spawn("native-recipient-browser", executable,
        f"--user-data-dir={profile}", "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1", "--no-first-run",
        "--no-default-browser-check", "--ignore-certificate-errors", "about:blank",
        env=dict(os.environ))
    port_file = profile / "DevToolsActivePort"
    async with asyncio.timeout(20):
        while not port_file.is_file():
            if child.returncode is not None:
                raise PrerequisiteFailure("REQUESTED_NATIVE_BROWSER_EXITED")
            await asyncio.sleep(0.02)
    port = int(port_file.read_text().splitlines()[0])
    # Public no_defaults applies to the real default context, unlike a second
    # CDP session which cannot undo Playwright's own forced-visible session.
    native = await playwright.chromium.connect_over_cdp(
        f"http://127.0.0.1:{port}", no_defaults=True)
    context = native.contexts[0]
    page = context.pages[0]
    await page.set_viewport_size({"width": 1365, "height": 900})
    return native, context, page


async def wait_visible(locator, timeout: int = 15000) -> None:
    await locator.wait_for(state="visible", timeout=timeout)


async def register(page, email: str, password: str, name: str, record: dict, tag: str) -> None:
    target = urlsplit(page.url)
    await page.goto(f"{target.scheme}://{target.netloc}/register", wait_until="domcontentloaded")
    await page.bring_to_front()
    await page.get_by_label("電子郵件").fill(email)
    await page.get_by_label("顯示名稱").fill(name)
    await page.get_by_label("密碼").fill(password)
    async with page.expect_response(
            lambda response: response.url.endswith("/api/v1/auth/register") and response.request.method == "POST") as registration:
        await page.get_by_role("button", name="建立帳號").click()
    response = await registration.value
    check(record, f"{tag}_registration_completed_in_real_ui", response.status == 201)
    await wait_visible(page.get_by_role("status"))


async def login(page, email: str, password: str, record: dict, tag: str) -> None:
    target = urlsplit(page.url)
    await page.goto(f"{target.scheme}://{target.netloc}/login", wait_until="domcontentloaded")
    await page.bring_to_front()
    await page.get_by_label("電子郵件").fill(email)
    await page.get_by_label("密碼").fill(password)
    await page.get_by_role("button", name="登入").click()
    await page.wait_for_url(re.compile(r"/chats(?:$|/)"), timeout=20000)
    await page.get_by_role("navigation", name="主要導覽").wait_for(state="visible")
    check(record, f"{tag}_login_reached_authenticated_shell", True)


async def public_id(page) -> str:
    await page.bring_to_front()
    await page.get_by_role("navigation", name="主要導覽").get_by_role("button", name="個人檔案").click()
    field = page.get_by_label("公開 ID（分享給對方以加入聯絡人）")
    await wait_visible(field)
    value = await field.input_value()
    if not value:
        raise AcceptanceFailure("PROFILE_PUBLIC_ID_NOT_RENDERED")
    return value


async def goto_chat_list(page) -> None:
    await page.bring_to_front()
    await page.get_by_role("navigation", name="主要導覽").get_by_role("button", name="聊天", exact=True).click()
    await page.wait_for_url(re.compile(r"/chats$"))
    await page.locator(".chat-list").wait_for(state="visible")


async def open_direct(page, recipient_id: str, record: dict) -> str:
    await page.bring_to_front()
    await page.get_by_role("navigation", name="主要導覽").get_by_role("button", name="聯絡人").click()
    await page.wait_for_url(re.compile(r"/contacts$"))
    await page.get_by_label("已知公開 ID").fill(recipient_id)
    await page.get_by_role("button", name="查詢").click()
    await page.get_by_role("button", name="開始聊天").wait_for(state="visible", timeout=15000)
    await page.get_by_role("button", name="開始聊天").click()
    await page.wait_for_url(re.compile(r"/chats/[^/]+$"), timeout=15000)
    await page.locator(".chat-room").wait_for(state="visible")
    conversation_id = page.url.rstrip("/").rsplit("/", 1)[-1]
    check(record, "direct_conversation_created_by_real_contact_ui", bool(conversation_id))
    return conversation_id


async def send_text(page, text: str) -> None:
    await page.bring_to_front()
    composer = page.locator(".chat-composer textarea")
    await composer.fill(text)
    await page.locator(".send-button").click()


async def wait_message(page, text: str, timeout: int = 30000) -> None:
    await page.locator("[data-message-id]").filter(has_text=text).first.wait_for(state="visible", timeout=timeout)


async def indexed_db_state(page, conversation_id: str, owner_device_id: str | None = None) -> dict:
    return await page.evaluate("""async ([conversationId, ownerDeviceId]) => {
      const request = indexedDB.open('hine-chat-v1');
      const db = await new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const bindings = JSON.parse(localStorage.getItem('hine-device-store') || '{"owners":{}}');
      const owner = Object.entries(bindings.owners || {}).find(([, value]) =>
        ownerDeviceId === null || value.device_id === ownerDeviceId);
      const ownerKey = owner ? JSON.stringify([owner[0], owner[1].device_id]) : null;
      const transaction = db.transaction(['partitions', 'drafts'], 'readonly');
      const read = request => new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const draftsRequest = read(transaction.objectStore('drafts').getAll());
      const ownerRequest = ownerKey === null ? Promise.resolve(null)
        : read(transaction.objectStore('partitions').get(ownerKey));
      const [drafts, ownerPartition] = await Promise.all([draftsRequest, ownerRequest]);
      db.close();
      const partition = ownerPartition && ownerPartition.messages && ownerPartition.conversations
        && ownerPartition.conversations[conversationId] ? ownerPartition : null;
      return {partition, ownerPartition: ownerPartition ?? null, drafts};
    }""", [conversation_id, owner_device_id])


async def indexeddb_persisted_message(page, conversation_id: str, text: str) -> bool:
    state = await indexed_db_state(page, conversation_id)
    return bool(state["partition"] and any(
        message.get("text") == text
        for message in state["partition"].get("messages", {}).get(conversation_id, [])
    ))


async def indexeddb_intent(page, conversation_id: str, text: str) -> dict | None:
    state = await indexed_db_state(page, conversation_id)
    if not state["partition"]:
        return None
    return next((intent for intent in state["partition"]["intents"].values()
                 if intent["conversationId"] == conversation_id
                 and intent["payload"].get("text") == text), None)


async def run_browser(args, evidence: dict, private: Path) -> int:
    # Product services and the browser share a single newly-owned native stack.
    sys.path.insert(0, str(ROOT / "backend/api/src"))
    sys.path.insert(0, str(ROOT / "backend/realtime/src"))
    spec = importlib.util.spec_from_file_location("hine_product_fault_drill", FAULTS)
    if spec is None or spec.loader is None:
        raise PrerequisiteFailure("NATIVE_COMPONENTS_UNAVAILABLE")
    fault = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fault
    spec.loader.exec_module(fault)
    from playwright.async_api import async_playwright

    test_record = evidence["scenario"]
    temp_web = private / "production-web"
    temp_web.mkdir(mode=0o700)
    native_ports, native_sockets = reserve_ports(5)
    origin = f"https://localhost:{native_ports[4]}"
    components_args = argparse.Namespace(postgres_bin=args.postgres_bin,
        redis_server=args.redis_server, caddy=args.caddy, python=args.python,
        web_root=str(temp_web))
    components = fault.Components(components_args)
    components.sockets = native_sockets
    ports = iter(native_ports)
    components.port = lambda: next(ports)
    browser = None
    native_receiver = None
    contexts = []
    pages = []
    try:
        await build_web(args.bun, temp_web, origin, private)
        bun_version, frontend_inputs, built_assets, bun_executable_hash = await web_build_provenance(args.bun, temp_web)
        evidence["environment"]["bun"] = bun_version
        evidence["provenance"].update({
            "bun_version": bun_version,
            "bun_executable_sha256": bun_executable_hash,
            "frontend_build_inputs_sha256": frontend_inputs,
            "production_web_assets_sha256": built_assets,
        })
        test_record["counts"]["frontend_build_inputs"] = len(frontend_inputs)
        test_record["counts"]["production_web_assets"] = len(built_assets)
        native_evidence = {}
        try:
            await fault.prerequisites(components_args, native_evidence)
        except fault.PrerequisiteFailure as failure:
            raise PrerequisiteFailure(str(failure)) from None
        evidence["provenance"].update(native_evidence["provenance"])
        evidence["environment"].update(native_evidence["environment"])
        check(test_record, "production_web_build_has_frontend_inputs_bun_and_asset_provenance",
              bool(evidence["provenance"]["frontend_build_inputs_sha256"]) and
              "index.html" in evidence["provenance"]["production_web_assets_sha256"] and
              evidence["environment"]["bun"] == bun_version)
        evidence["provenance"].update({
            "browser_runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "native_bundle_sha256": hashlib.sha256((ROOT / "tests/browser/native-acceptance.ts").read_bytes()).hexdigest(),
        })
        evidence["environment"]["playwright"] = "1.63.0"
        check(test_record, "native_fault_prerequisites_attested_real_toolchain", True)
        await components.__aenter__()
        check(test_record, "owned_native_api_ba_postgresql17_redis_caddy_started", True)
        async with components.sql() as conn:
            postgres_version = await conn.fetchval("SELECT current_setting('server_version_num')::integer")
        check(test_record, "actual_owned_postgresql17_available", postgres_version // 10000 == 17)
        check(test_record, "actual_owned_redis_authenticated_and_available", await components.redis.ping())
        async with async_playwright() as playwright:
            launch = {"headless": not args.headed}
            if args.browser_executable:
                browser_type = playwright.chromium
                launch["executable_path"] = args.browser_executable
            elif args.browser == "chromium":
                browser_type = playwright.chromium
            else:
                browser_type = playwright.chromium
                launch["channel"] = args.browser
            # Caddy's private local CA is not installed in the browser's system
            # trust store. Components independently verifies TLS against that CA.
            try:
                browser = await browser_type.launch(**launch)
            except PlaywrightError:
                raise PrerequisiteFailure("REQUESTED_BROWSER_CHANNEL_UNAVAILABLE") from None
            context_a = await browser.new_context(base_url=origin, ignore_https_errors=True, viewport={"width": 1365, "height": 900})
            page_a = await context_a.new_page()
            if args.headed:
                native_receiver, context_b, page_b = await _native_recipient(playwright, args, components, private)
                evidence["configuration"]["recipient_focus_emulation"] = False
                evidence["environment"]["native_recipient_browser_version"] = native_receiver.version
            else:
                context_b = await browser.new_context(base_url=origin, ignore_https_errors=True, viewport={"width": 1365, "height": 900})
                page_b = await context_b.new_page()
            contexts.extend([context_a, context_b])
            pages.extend([page_a, page_b])
            observed_websockets: list[str] = []
            page_a.on("websocket", lambda websocket: observed_websockets.append(websocket.url))
            page_b.on("websocket", lambda websocket: observed_websockets.append(websocket.url))
            await page_a.goto(origin + "/")
            await page_b.goto(origin + "/")
            test_record["checks"]["real_browser_https_production_build_loaded"] = await page_a.locator("#root").evaluate("(root) => root.childElementCount > 0") and await page_b.locator("#root").evaluate("(root) => root.childElementCount > 0")
            test_record["checks"]["real_browser_secure_context"] = await page_a.evaluate("isSecureContext && location.protocol === 'https:'")
            check(test_record, "real_browser_https_production_build_loaded", test_record["checks"]["real_browser_https_production_build_loaded"])
            check(test_record, "real_browser_secure_context", test_record["checks"]["real_browser_secure_context"])

            emails = [secrets.token_hex(12) + "@owned.browser.test" for _ in range(2)]
            password = secrets.token_urlsafe(24) + "A1!"
            names = ["Owned Browser Alice " + secrets.token_hex(3), "Owned Browser Bob " + secrets.token_hex(3)]
            await register(page_a, emails[0], password, names[0], test_record, "alice")
            await register(page_b, emails[1], password, names[1], test_record, "bob")
            await login(page_a, emails[0], password, test_record, "alice")
            await login(page_b, emails[1], password, test_record, "bob")
            ids = [await public_id(page_a), await public_id(page_b)]
            check(test_record, "independently_registered_accounts_have_distinct_real_public_ids", ids[0] != ids[1])
            device_a = await page_a.evaluate("JSON.parse(localStorage.getItem('hine-device-store')).owners[Object.keys(JSON.parse(localStorage.getItem('hine-device-store')).owners)[0]].device_id")
            device_b = await page_b.evaluate("JSON.parse(localStorage.getItem('hine-device-store')).owners[Object.keys(JSON.parse(localStorage.getItem('hine-device-store')).owners)[0]].device_id")
            await goto_chat_list(page_a)
            direct_id = await open_direct(page_a, ids[1], test_record)
            async with components.sql() as conn:
                direct = await conn.fetchrow("SELECT conversation_id,type FROM conversations WHERE conversation_id=$1", direct_id)
                direct_members = await conn.fetchval("SELECT count(*) FROM memberships WHERE conversation_id=$1 AND active", direct_id)
            check(test_record, "direct_creation_persisted_real_database", direct is not None and direct["type"] == "direct" and direct_members == 2)
            # UI-created direct chat must also reach the recipient through the
            # actual websocket, persisted projection, and real IndexedDB.
            direct_message = "browser-direct-" + secrets.token_hex(8)
            await send_text(page_a, direct_message)
            await wait_message(page_a, direct_message)
            await page_b.goto(origin + "/chats/" + quote(direct_id, safe=""), wait_until="domcontentloaded")
            await page_b.bring_to_front()
            await wait_message(page_b, direct_message, 45000)
            check(test_record, "recipient_direct_message_rendered_from_real_wss", True)
            check(test_record, "recipient_direct_message_persisted_in_native_indexeddb", await indexeddb_persisted_message(page_b, direct_id, direct_message))

            # Receipt transitions are confirmed by persisted SQL, not only a
            # presentation label. Visibility testing is explicitly headed-only.
            async with components.sql() as conn:
                row = await conn.fetchrow("SELECT message_id,client_message_id FROM messages WHERE payload->>'text'=$1", direct_message)
                original_count = await conn.fetchval("SELECT count(*) FROM messages WHERE client_message_id=$1", row["client_message_id"]) if row else 0
            check(test_record, "direct_message_has_one_sql_persisted_original", row is not None and original_count == 1)
            if row is None:
                raise AcceptanceFailure("DIRECT_MESSAGE_SQL_ROW_MISSING")
            direct_c1 = row["client_message_id"]
            direct_m1 = row["message_id"]
            async with asyncio.timeout(20):
                while True:
                    async with components.sql() as conn:
                        receipt_status = await conn.fetchval(
                            "SELECT status FROM receipts WHERE message_id=$1 AND user_id=$2",
                            row["message_id"], ids[1])
                    if receipt_status == "read":
                        break
                    await asyncio.sleep(0.2)
            check(test_record, "visible_recipient_receipt_committed_as_read", receipt_status == "read")
            await page_a.wait_for_function(
                "id => [...document.querySelectorAll('[data-message-id]')].some(node => node.dataset.messageId === id && node.querySelector('.message-meta')?.textContent.includes('已讀'))",
                arg=str(direct_m1), timeout=20000)
            sender_receipt_state = await indexed_db_state(page_a, direct_id, device_a)
            sender_message = next((message for message in sender_receipt_state["partition"]["messages"][direct_id]
                                   if message["id"] == str(direct_m1)), None)
            check(test_record, "sender_real_bubble_and_idb_project_recipient_read_receipt",
                  sender_message is not None and sender_message["receipt"]["status"] == "read"
                  and sender_receipt_state["partition"]["statuses"][str(direct_m1)]["status"] == "read")
            if args.headed:
                cover = await context_b.new_page()
                pages.append(cover)
                await cover.goto(origin + "/", wait_until="domcontentloaded")
                await cover.bring_to_front()
                await page_b.wait_for_function("document.visibilityState === 'hidden'", polling=100, timeout=10000)
                check(test_record, "headed_recipient_page_is_genuinely_hidden", await page_b.evaluate("document.visibilityState === 'hidden'"))
                hidden_message = "browser-hidden-" + secrets.token_hex(8)
                await send_text(page_a, hidden_message)
                await page_b.wait_for_function(
                    "text => [...document.querySelectorAll('[data-message-id]')].some(node => node.textContent.includes(text))",
                    arg=hidden_message, timeout=30000, polling=100)
                async with components.sql() as conn:
                    hidden_row = await conn.fetchrow("SELECT message_id FROM messages WHERE payload->>'text'=$1", hidden_message)
                hidden_status = None
                hidden_deadline = time.monotonic() + 20
                while time.monotonic() < hidden_deadline:
                    async with components.sql() as conn:
                        hidden_status = await conn.fetchval(
                            "SELECT status FROM receipts WHERE message_id=$1 AND user_id=$2",
                            hidden_row["message_id"], ids[1])
                    if hidden_status == "read":
                        check(test_record, "hidden_recipient_never_commits_read_while_hidden", False)
                    if hidden_status == "delivered":
                        break
                    await asyncio.sleep(0.1)
                check(test_record, "hidden_recipient_message_stays_delivered_not_read",
                      hidden_status == "delivered" and await page_b.evaluate("document.visibilityState === 'hidden'"))
                await page_b.bring_to_front()
                await page_b.wait_for_function("document.visibilityState === 'visible'", polling=100, timeout=10000)
                await page_b.wait_for_function(
                    "id => document.querySelector(`[data-message-id='${id}']`)?.dataset.readEligible === 'false'",
                    arg=str(hidden_row["message_id"]), timeout=20000)
                receipt_deadline = time.monotonic() + 20
                status = None
                while time.monotonic() < receipt_deadline:
                    async with components.sql() as conn:
                        status = await conn.fetchval(
                            "SELECT status FROM receipts WHERE message_id=$1 AND user_id=$2",
                            hidden_row["message_id"], ids[1])
                    if status == "read":
                        break
                    await asyncio.sleep(0.1)
                check(test_record, "visible_recipient_read_observer_commits_read_receipt", status == "read")
                await cover.close()
            else:
                test_record["unexercised"].append("headed-only-native-hidden-read-observation")

            # Keep a real user draft in the browser's native database through a
            # physical page reload; independently prove the owner device binding.
            draft = "browser-reload-draft-" + secrets.token_hex(6)
            await page_a.locator(".chat-composer textarea").fill(draft)
            await page_a.wait_for_function("async text => { const request=indexedDB.open('hine-chat-v1'); const db=await new Promise((r,j)=>{request.onsuccess=()=>r(request.result);request.onerror=()=>j(request.error)}); const tx=db.transaction('drafts','readonly');const rows=await new Promise((r,j)=>{const q=tx.objectStore('drafts').getAll();q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error)});db.close();return rows.some(row=>row.value===text)}", arg=draft)
            await page_a.reload(wait_until="domcontentloaded")
            await page_a.wait_for_function("() => document.querySelector('.chat-room') !== null", timeout=45000)
            await page_a.wait_for_function("text => document.querySelector('.chat-composer textarea')?.value === text", arg=draft)
            device_after = await page_a.evaluate("JSON.parse(localStorage.getItem('hine-device-store')).owners[Object.keys(JSON.parse(localStorage.getItem('hine-device-store')).owners)[0]].device_id")
            async with components.sql() as conn:
                post_reload_count = await conn.fetchval("SELECT count(*) FROM messages WHERE client_message_id=$1", direct_c1)
                post_reload_m1 = await conn.fetchval("SELECT message_id FROM messages WHERE client_message_id=$1", direct_c1)
            check(test_record, "same_original_c1_maps_to_same_persisted_m1_after_reload_and_reconnect",
                  post_reload_count == 1 and post_reload_m1 == direct_m1)
            check(test_record, "physical_reload_restores_draft_from_indexeddb", await page_a.locator(".chat-composer textarea").input_value() == draft)
            check(test_record, "physical_reload_preserves_device_id", device_after == device_a)
            uncertain_text = "browser-committed-response-loss-" + secrets.token_hex(8)
            components.api_link.drop_write = True
            await send_text(page_a, uncertain_text)
            drop_deadline = time.monotonic() + 20
            while components.api_link.dropped != 1 and time.monotonic() < drop_deadline:
                await asyncio.sleep(0.01)
            check(test_record, "real_persist_if_absent_response_was_dropped_after_commit",
                  components.api_link.dropped == 1 and not components.api_link.drop_write)
            async with components.sql() as conn:
                uncertain_rows = await conn.fetch(
                    "SELECT message_id,client_message_id,payload->>'text' AS text FROM messages WHERE payload->>'text'=$1",
                    uncertain_text)
            uncertain_intent = await indexeddb_intent(page_a, direct_id, uncertain_text)
            check(test_record, "original_committed_response_loss_kept_one_unconfirmed_c1_before_reload",
                  len(uncertain_rows) == 1 and uncertain_rows[0]["text"] == uncertain_text
                  and uncertain_intent is not None
                  and uncertain_intent["clientMessageId"] == str(uncertain_rows[0]["client_message_id"])
                  and uncertain_intent["status"] == "unknown" and uncertain_intent["messageId"] is None
                  and uncertain_intent["payload"] == {"type": "text", "text": uncertain_text})
            uncertain_c1 = uncertain_intent["clientMessageId"]
            await page_a.reload(wait_until="domcontentloaded")
            await page_a.wait_for_function("() => document.querySelector('.chat-room') !== null", timeout=45000)
            await page_a.wait_for_function(
                "() => document.querySelector('.chat-header small[role=status]')?.textContent.includes('即時連線')",
                timeout=45000)
            await wait_message(page_a, uncertain_text, timeout=45000)
            async with components.sql() as conn:
                replay_rows = await conn.fetch(
                    "SELECT message_id,client_message_id,payload->>'text' AS text FROM messages WHERE client_message_id=$1",
                    uncertain_c1)
            restored_intent = await indexeddb_intent(page_a, direct_id, uncertain_text)
            uncertain_m1 = str(uncertain_rows[0]["message_id"])
            uncertain_dom_count = await page_a.locator(f"[data-message-id='{uncertain_m1}']").count()
            check(test_record, "genuine_reload_replays_same_unconfirmed_c1_to_same_single_m1",
                  len(replay_rows) == 1 and str(replay_rows[0]["message_id"]) == uncertain_m1
                  and str(replay_rows[0]["client_message_id"]) == uncertain_c1
                  and replay_rows[0]["text"] == uncertain_text and uncertain_dom_count == 1
                  and restored_intent is not None
                  and restored_intent["clientMessageId"] == uncertain_c1
                  and restored_intent["messageId"] == uncertain_m1
                  and restored_intent["status"] == "persisted"
                  and restored_intent["payload"] == {"type": "text", "text": uncertain_text})

            # Exercise real saved-cursor recipient recovery: disconnect the
            # recipient browser, commit 100 normal sender messages, then let
            # that browser reconnect and recover through its saved cursor.
            cursor_before = (await indexed_db_state(page_b, direct_id))["partition"]["cursor"]
            check(test_record, "recipient_has_persisted_pre_disconnect_cursor", isinstance(cursor_before, str) and bool(cursor_before))
            await page_b.context.set_offline(True)
            await page_b.wait_for_function("() => !navigator.onLine")
            recovery_text = [f"browser-recovery-{i:03d}-" + secrets.token_hex(3) for i in range(100)]
            for text in recovery_text:
                await send_text(page_a, text)
                await wait_message(page_a, text, timeout=90000)
            check(test_record, "recovery_messages_committed_while_recipient_offline", True)
            absent_offline = await page_b.evaluate(
                "(texts) => texts.every(text => ![...document.querySelectorAll('[data-message-id]')].some(node => node.textContent.includes(text)))",
                recovery_text)
            check(test_record, "recipient_offline_page_did_not_present_new_messages", absent_offline)
            async with components.sql() as conn:
                rows = await conn.fetch("SELECT message_id,client_message_id,payload->>'text' AS text FROM messages WHERE payload->>'text'=ANY($1::text[])", recovery_text)
            check(test_record, "one_hundred_original_offline_interval_messages_persist_once", len(rows) == 100 and len({row["client_message_id"] for row in rows}) == 100)
            test_record["counts"]["recipient_offline_messages_recovered"] = len(rows)
            recovery_started = time.monotonic()
            await page_b.context.set_offline(False)
            await page_b.bring_to_front()
            expected_messages = [[str(row["message_id"]), row["text"]] for row in rows]
            await page_b.wait_for_function("""expected => {
              const nodes = new Map([...document.querySelectorAll('[data-message-id]')]
                .map(node => [node.dataset.messageId, node.textContent]));
              return expected.every(([id, text]) => nodes.get(id)?.includes(text));
            }""", arg=expected_messages, timeout=15000)
            await page_b.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            recovered_state = await indexed_db_state(page_b, direct_id, device_b)
            recovered_messages = recovered_state["partition"]["messages"][direct_id]
            indexed_results = []
            for message_id, text in expected_messages:
                matches = [message for message in recovered_messages if message["id"] == message_id]
                indexed_results.append(len(matches) == 1 and matches[0].get("text") == text)
            dom_results = await page_b.evaluate("""expected => {
              const nodes = [...document.querySelectorAll('[data-message-id]')];
              return expected.map(([id, text]) => {
                const matches = nodes.filter(node => node.dataset.messageId === id);
                return matches.length === 1 && matches[0].textContent.includes(text);
              });
            }""", expected_messages)
            recovery_ms = round((time.monotonic() - recovery_started) * 1000, 2)
            check(test_record, "one_hundred_messages_recovered_once_per_m1_in_recipient_dom",
                  len(dom_results) == 100 and all(dom_results))
            check(test_record, "one_hundred_messages_recovered_once_per_m1_in_recipient_indexeddb",
                  len(indexed_results) == 100 and all(indexed_results))
            check(test_record, "recipient_saved_cursor_advanced_after_real_reconnect", recovered_state["partition"]["cursor"] != cursor_before)
            check(test_record, "native_recipient_recovery_completed_within_five_seconds", recovery_ms <= 5000)
            test_record["timings_ms"] = {"recipient_offline_to_100_dom_and_idb_recovery": recovery_ms}
            sender_intent_text = "browser-sender-offline-" + secrets.token_hex(8)
            await page_a.context.set_offline(True)
            await page_a.wait_for_function("() => !navigator.onLine")
            await send_text(page_a, sender_intent_text)
            await page_a.wait_for_function("""async text => {
              const request=indexedDB.open('hine-chat-v1');
              const db=await new Promise((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
              const values=await new Promise((resolve,reject)=>{const query=db.transaction('partitions','readonly').objectStore('partitions').getAll();query.onsuccess=()=>resolve(query.result);query.onerror=()=>reject(query.error)});
              db.close();
              return values.some(partition=>Object.values(partition.intents||{}).some(intent=>intent.payload?.text===text&&intent.status!=='persisted'));
            }""", arg=sender_intent_text)
            saved_intent = await indexeddb_intent(page_a, direct_id, sender_intent_text)
            check(test_record, "sender_offline_message_keeps_original_indexeddb_c1", saved_intent is not None and bool(saved_intent["clientMessageId"]))
            sender_c1 = saved_intent["clientMessageId"]
            await page_a.context.set_offline(False)
            await wait_message(page_a, sender_intent_text, timeout=90000)
            await wait_message(page_b, sender_intent_text, timeout=90000)
            async with components.sql() as conn:
                sender_rows = await conn.fetch(
                    "SELECT message_id,payload->>'text' AS text FROM messages WHERE client_message_id=$1", sender_c1)
            persisted_sender_intent = await indexeddb_intent(page_a, direct_id, sender_intent_text)
            check(test_record, "same_sender_offline_c1_maps_to_one_original_persisted_message",
                  len(sender_rows) == 1 and sender_rows[0]["text"] == sender_intent_text
                  and persisted_sender_intent is not None
                  and persisted_sender_intent["clientMessageId"] == sender_c1
                  and persisted_sender_intent["messageId"] == str(sender_rows[0]["message_id"]))

            # Create a real group through the UI, prove original membership and
            # group message persistence, inspect real modal and responsive shell.
            await goto_chat_list(page_a)
            await page_a.get_by_role("button", name=re.compile("建立群組")).click()
            group_title = "Browser group " + secrets.token_hex(5)
            await page_a.get_by_label("群組名稱").fill(group_title)
            await page_a.get_by_label("初始成員公開 ID（每行一位）").fill(ids[1])
            await page_a.get_by_role("button", name="建立群組並開啟").click()
            await page_a.wait_for_url(re.compile(r"/chats/[^/]+$"), timeout=20000)
            await page_a.get_by_role("heading", name=group_title).wait_for(state="visible")
            group_id = page_a.url.rstrip("/").rsplit("/", 1)[-1]
            async with components.sql() as conn:
                group = await conn.fetchrow("SELECT conversation_id,type,title #>> '{}' AS title FROM conversations WHERE conversation_id=$1", group_id)
                members = await conn.fetchval("SELECT count(*) FROM memberships WHERE conversation_id=$1 AND active", group_id)
                persisted_intents = await conn.fetchval(
                    "SELECT count(*) FROM mutation_keys WHERE user_id=$1 AND operation='A14' AND payload->>'title'=$2 AND result->>'id'=$3",
                    ids[0], group_title, group_id)
            check(test_record, "group_creation_preserves_original_title_members_and_intent", group is not None and group["type"] == "group" and group["title"] == group_title and members == 2 and persisted_intents == 1)
            group_message = "browser-group-" + secrets.token_hex(8)
            await send_text(page_a, group_message)
            await wait_message(page_a, group_message)
            await page_b.goto(origin + "/chats/" + quote(group_id, safe=""), wait_until="domcontentloaded")
            await page_b.bring_to_front()
            await wait_message(page_b, group_message, timeout=45000)
            check(test_record, "group_recipient_dom_and_indexeddb_message_persisted", await indexeddb_persisted_message(page_b, group_id, group_message))
            async with components.sql() as conn:
                group_message_row = await conn.fetchrow(
                    "SELECT message_id,client_message_id FROM messages WHERE conversation_id=$1 AND payload->>'text'=$2",
                    group_id, group_message)
                group_mapping_count = await conn.fetchval(
                    "SELECT count(*) FROM messages WHERE client_message_id=$1",
                    group_message_row["client_message_id"]) if group_message_row else 0
            check(test_record, "group_message_original_intent_persisted_once", group_message_row is not None and group_mapping_count == 1)
            await page_a.get_by_role("button", name="群組資訊").click()
            dialog = page_a.get_by_role("dialog", name="群組資訊")
            await wait_visible(dialog)
            check(test_record, "group_info_native_modal_visible_and_accessible", await dialog.get_attribute("aria-modal") == "true")
            await dialog.get_by_role("button", name="關閉群組資訊").click()
            check(test_record, "group_info_modal_closes", await dialog.count() == 0)
            await page_a.set_viewport_size({"width": 390, "height": 844})
            await page_a.wait_for_timeout(200)
            dimensions = await page_a.evaluate("({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,nav:getComputedStyle(document.querySelector('.app-nav')).position})")
            check(test_record, "responsive_mobile_shell_has_no_horizontal_overflow", dimensions["scroll"] <= dimensions["width"])
            check(test_record, "responsive_mobile_navigation_is_sticky", dimensions["nav"] == "sticky")
            await page_a.get_by_role("button", name="群組資訊").click()
            mobile_dialog = page_a.get_by_role("dialog", name="群組資訊")
            await wait_visible(mobile_dialog)
            mobile_bounds = await mobile_dialog.evaluate("(dialog) => { const rect=dialog.getBoundingClientRect(); return {width:rect.width,height:rect.height,viewportWidth:innerWidth,viewportHeight:innerHeight}; }")
            check(test_record, "responsive_group_modal_fits_mobile_viewport", mobile_bounds["width"] <= mobile_bounds["viewportWidth"] and mobile_bounds["height"] <= mobile_bounds["viewportHeight"])
            await mobile_dialog.get_by_role("button", name="關閉群組資訊").click()

            # Real membership invalidation: admin removes recipient through the
            # application UI, then receiver must evict stale group content.
            await page_a.get_by_role("button", name="群組資訊").click()
            await wait_visible(page_a.get_by_role("dialog", name="群組資訊"))
            await page_a.get_by_role("button", name="前往群組管理").click()
            await page_a.wait_for_url(re.compile(r"/groups/[^/]+/manage$"), timeout=15000)
            remove = page_a.locator(".member-list li").filter(has_text=ids[1]).get_by_role("button", name="移除", exact=True)
            await wait_visible(remove)
            async with page_a.expect_response(
                    lambda response: response.url.endswith(f"/api/v1/conversations/{quote(group_id, safe='')}/members/{quote(ids[1], safe='')}") and response.request.method == "DELETE") as removal:
                await remove.click()
            check(test_record, "real_group_member_removal_http_committed", (await removal.value).status == 204)
            await page_b.wait_for_url(re.compile(r"/chats$"), timeout=30000)
            state_after_revoke = await indexed_db_state(page_b, group_id, device_b)
            revoked_owner = state_after_revoke["ownerPartition"]
            check(test_record, "real_group_invalidation_redirects_removed_recipient", page_b.url.endswith("/chats"))
            check(test_record, "real_group_invalidation_erases_revoked_owner_cache_without_metadata",
                  revoked_owner is not None
                  and group_id not in revoked_owner.get("conversations", {})
                  and group_id not in revoked_owner.get("messages", {}))
            async with components.sql() as conn:
                final_members = await conn.fetchval("SELECT count(*) FROM memberships WHERE conversation_id=$1 AND active", group_id)
            check(test_record, "real_group_removal_persisted_in_sql", final_members == 1)
            test_record["counts"]["group_members_after_ui_removal"] = int(final_members)
            context_c = await browser.new_context(base_url=origin, ignore_https_errors=True, viewport={"width": 1365, "height": 900})
            contexts.append(context_c)
            page_c = await context_c.new_page()
            page_c.on("websocket", lambda websocket: observed_websockets.append(websocket.url))
            pages.append(page_c)
            await page_c.goto("/")
            await login(page_c, emails[0], password, test_record, "alice_independent_device")
            device_a2 = await page_c.evaluate("JSON.parse(localStorage.getItem('hine-device-store')).owners[Object.keys(JSON.parse(localStorage.getItem('hine-device-store')).owners)[0]].device_id")
            async with components.sql() as conn:
                same_user_devices = await conn.fetchrow(
                    "SELECT count(*) AS devices,count(DISTINCT subject_id) AS subjects FROM devices WHERE device_id=ANY($1::text[])",
                    [device_a, device_a2])
            check(test_record, "same_account_independent_browser_has_distinct_real_device", device_a2 != device_a and same_user_devices["devices"] == 2 and same_user_devices["subjects"] == 1)
            await page_c.goto("/chats/" + quote(direct_id, safe=""))
            await page_c.bring_to_front()
            await page_c.locator(".chat-room").wait_for(state="visible")
            async with page_a.expect_response(
                    lambda response: response.url.endswith("/api/v1/auth/logout") and response.request.method == "POST") as logout_info:
                await page_a.get_by_role("button", name="登出").click()
            logout_response = await logout_info.value
            check(test_record, "real_ui_logout_received_committed_http_204", logout_response.status == 204)
            await page_a.wait_for_url(re.compile(r"/login$"), timeout=15000)
            async with components.sql() as conn:
                logout_row = await conn.fetchrow(
                    "SELECT s.revoked,i.reason FROM sessions s JOIN session_invalidations i USING(session_id) WHERE s.device_id=$1 AND i.reason='logout' ORDER BY i.committed_at DESC LIMIT 1",
                    device_a)
                surviving_device_sessions = await conn.fetchval(
                    "SELECT count(*) FROM sessions WHERE device_id=$1 AND NOT revoked", device_a2)
            check(test_record, "real_logout_revoked_original_device_session", logout_row is not None and logout_row["revoked"] and logout_row["reason"] == "logout")
            check(test_record, "real_logout_preserved_same_users_independent_device_session", surviving_device_sessions == 1)
            async with page_c.expect_response(
                    lambda response: response.url.endswith("/api/v1/users/me") and response.request.method == "GET") as profile_info:
                await page_c.get_by_role("navigation", name="主要導覽").get_by_role("button", name="個人檔案").click()
            profile_response = await profile_info.value
            check(test_record, "independent_device_real_authenticated_http_survives_logout", profile_response.status == 200)
            await page_c.go_back()
            await page_c.locator(".chat-room").wait_for(state="visible")
            surviving_message = "browser-surviving-device-" + secrets.token_hex(8)
            await send_text(page_c, surviving_message)
            await wait_message(page_c, surviving_message)
            await page_b.goto(origin + "/chats/" + quote(direct_id, safe=""), wait_until="domcontentloaded")
            await page_b.bring_to_front()
            await wait_message(page_b, surviving_message)
            async with components.sql() as conn:
                surviving_rows = await conn.fetch(
                    "SELECT sender_id,client_message_id FROM messages WHERE conversation_id=$1 AND payload->>'text'=$2",
                    direct_id, surviving_message)
            check(test_record, "independent_device_real_websocket_survives_logout",
                  len(surviving_rows) == 1 and surviving_rows[0]["sender_id"] == ids[0])

            tls_context = components.http.connector._ssl
            check(test_record, "owned_tls_client_requires_ca_and_hostname_verification",
                  isinstance(tls_context, ssl.SSLContext)
                  and tls_context.verify_mode == ssl.CERT_REQUIRED and tls_context.check_hostname)
            check(test_record, "real_same_origin_websocket_used", any(
                url == f"wss://localhost:{components.tls_port}/ws/v1" for url in observed_websockets))
            evidence["environment"]["browser_version"] = browser.version
            evidence["environment"]["browser_selection"] = (
                "executable:" + Path(args.browser_executable).name if args.browser_executable else args.browser)
            evidence["environment"]["headed"] = args.headed
            return 0
    finally:
        for page in reversed(pages):
            with contextlib.suppress(Exception):
                await page.close()
        for context in reversed(contexts):
            with contextlib.suppress(Exception):
                await context.close()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if native_receiver is not None:
            with contextlib.suppress(Exception):
                await native_receiver.close()
        await components.close()


def valid_exec(path: str | None) -> bool:
    return bool(path and Path(path).is_file() and os.access(path, os.X_OK))


async def interruptible_run(args: argparse.Namespace, evidence: dict, private: Path) -> int:
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    interrupted = False

    def interrupt() -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            current.cancel()

    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, interrupt)
    try:
        return await run_browser(args, evidence, private)
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", required=True)
    parser.add_argument("--redis-server", required=True)
    parser.add_argument("--caddy", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--bun", required=True)
    parser.add_argument("--browser", choices=("chromium", "chrome", "msedge"), required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--output", required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if os.path.lexists(args.output):
        print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
        return 2
    parent = Path(args.output).absolute().parent
    try:
        fd, temporary_output = tempfile.mkstemp(dir=parent, prefix=".hine-browser-evidence-")
        os.close(fd)
        private = Path(tempfile.mkdtemp(prefix="hine-browser-acceptance-"))
        private.chmod(0o700)
    except OSError:
        print("OUTPUT_OR_PRIVATE_TEMP_UNAVAILABLE", file=sys.stderr)
        return 2
    record = {"status": "NOT_EXERCISED", "checks": {}, "counts": {}, "unexercised": []}
    evidence = {
        "schema_version": 1, "started_utc": now(), "completed_utc": None,
        "scope": "LOCAL_REAL_PRODUCTION_WEB_BROWSER_AND_NATIVE_PRODUCT",
        "status": "NOT_EXERCISED", "failure_code": None,
        "configuration": {"browser": args.browser, "headed": args.headed,
            "browser_executable_basename": Path(args.browser_executable).name if args.browser_executable else None,
            "production_web_build_in_owned_temp": True, "fresh_owned_native_services": True},
        "environment": {"os": platform.system(), "release": platform.release(),
            "architecture": platform.machine(), "python": platform.python_version()},
        "provenance": {}, "scenario": record, "limits": list(LIMITS),
        "transport_note": "Owned HTTP client verifies private Caddy CA; browser HTTPS/WSS uses that owned TLS endpoint with browser private-CA errors ignored.",
    }
    code = 2
    old_umask = os.umask(0o077)
    try:
        if platform.system() != "Linux" or os.geteuid() == 0:
            raise PrerequisiteFailure("NONROOT_LINUX_REQUIRED")
        for name in ("postgres-bin", "redis-server", "caddy", "python", "bun"):
            value = getattr(args, name.replace("-", "_"))
            if name == "postgres-bin":
                directory = Path(value)
                if not all((directory / binary).is_file() and os.access(directory / binary, os.X_OK)
                           for binary in ("initdb", "postgres", "pg_ctl", "createdb", "pg_dump", "pg_restore")):
                    raise PrerequisiteFailure("POSTGRES_17_TOOLS_UNAVAILABLE")
            elif not valid_exec(value):
                raise PrerequisiteFailure("REQUIRED_NATIVE_EXECUTABLE_UNAVAILABLE")
        if args.browser_executable and not valid_exec(args.browser_executable):
            raise PrerequisiteFailure("BROWSER_EXECUTABLE_UNAVAILABLE")
        if sys.version_info < (3, 12):
            raise PrerequisiteFailure("PYTHON_312_REQUIRED")
        evidence["environment"]["playwright"] = metadata_version("playwright")
        if evidence["environment"]["playwright"] != "1.63.0":
            raise PrerequisiteFailure("PLAYWRIGHT_1630_REQUIRED")
        metadata_version("aiohttp")
        metadata_version("asyncpg")
        evidence["provenance"] = {
            "browser_runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "native_bundle_sha256": hashlib.sha256((ROOT / "tests/browser/native-acceptance.ts").read_bytes()).hexdigest(),
            "authority": "EXISTING_UNMODIFIED_PRODUCT_FAULT_COMPONENTS",
            "playwright_version": "1.63.0",
        }
        code = asyncio.run(interruptible_run(args, evidence, private))
        record["status"] = "PASS" if code == 0 else "FAIL"
    except PrerequisiteFailure as failure:
        evidence["failure_code"] = str(failure)
        code = 2
    except AcceptanceFailure as failure:
        evidence["failure_code"] = failure.code
        evidence["failure_sites"] = _failure_sites(failure)
        record["status"] = "FAIL"
        code = 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        evidence["failure_code"] = "RUN_INTERRUPTED"
        record["status"] = "FAIL"
        code = 1
    except Exception as failure:  # noqa: BLE001 - sanitize arbitrary product/browser exceptions at the evidence boundary.
        evidence["failure_code"] = "REAL_PRODUCT_OR_BROWSER_RUNNER_ERROR"
        evidence["failure_sites"] = _failure_sites(failure)
        record["status"] = "FAIL" if record["checks"] else "NOT_EXERCISED"
        code = 1 if record["checks"] else 2
    finally:
        os.umask(old_umask)
        evidence["completed_utc"] = now()
        evidence["status"] = "PASS" if code == 0 else ("NOT_EXERCISED" if code == 2 else "FAIL")
        evidence["exit_code"] = code
        try:
            with os.fdopen(os.open(temporary_output, os.O_WRONLY | os.O_TRUNC, 0o600), "w", encoding="utf-8") as target:
                json.dump(evidence, target, ensure_ascii=True, indent=2, sort_keys=True)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.link(temporary_output, args.output)
            directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except FileExistsError:
            print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
            code = 2
        except OSError:
            print("OUTPUT_CANNOT_BE_PUBLISHED", file=sys.stderr)
            code = 2
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary_output)
            shutil.rmtree(private, ignore_errors=True)
        if code == evidence["exit_code"]:
            print("BROWSER_ACCEPTANCE_" + evidence["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
