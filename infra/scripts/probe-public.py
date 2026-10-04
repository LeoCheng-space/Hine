#!/usr/bin/env python3
"""Read-only production DNS/TLS/routing probe; never logs bodies or credentials."""
import base64
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys


def request(domain, path, *, secure=True):
    connection = (http.client.HTTPSConnection(domain, timeout=10, context=ssl.create_default_context())
                  if secure else http.client.HTTPConnection(domain, timeout=10))
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("probe response exceeded64KiB")
        return response.status, {key.lower(): value for key, value in response.getheaders()}, body
    finally:
        connection.close()


def validate_upgrade(header_block, key):
    lines = header_block.split("\r\n")
    status = lines[0].split()
    if len(status) < 2 or status[1] != "101":
        raise ValueError("exact /ws/v1 did not return HTTP101")
    headers = {}
    for line in lines[1:]:
        if not line:
            break
        name, value = line.split(":", 1)
        headers[name.lower()] = value.strip()
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    if headers.get("upgrade", "").lower() != "websocket":
        raise ValueError("WebSocket Upgrade response missing")
    if "upgrade" not in {token.strip().lower() for token in headers.get("connection", "").split(",")}:
        raise ValueError("WebSocket Connection upgrade response missing")
    if headers.get("sec-websocket-accept") != expected:
        raise ValueError("WebSocket accept hash invalid")


def probe_websocket(domain):
    key = base64.b64encode(os.urandom(16)).decode()
    with (
        socket.create_connection((domain, 443), timeout=10) as raw,
        ssl.create_default_context().wrap_socket(raw, server_hostname=domain) as transport,
    ):
        transport.sendall((f"GET /ws/v1 HTTP/1.1\r\nHost: {domain}\r\nOrigin: https://{domain}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                           f"Sec-WebSocket-Key: {key}\r\n\r\n").encode("ascii"))
        received = b""
        while b"\r\n\r\n" not in received:
            chunk = transport.recv(4096)
            if not chunk:
                raise ValueError("WebSocket handshake ended before response headers")
            received += chunk
            if len(received) > 32768:
                raise ValueError("WebSocket response headers exceeded32KiB")
        validate_upgrade(received.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1"), key)
        # Normal masked Close1000. No W01, token, write, or product test is sent.
        payload = b"\x03\xe8"
        mask = os.urandom(4)
        transport.sendall(b"\x88\x82" + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(payload)))


def main():
    domain = os.environ.get("HINE_DOMAIN")
    expected_text = os.environ.get("HINE_EXPECTED_IP")
    if not domain or not expected_text:
        raise ValueError("HINE_DOMAIN and HINE_EXPECTED_IP (comma-separated approved VM addresses) are required")
    expected = {str(ipaddress.ip_address(address.strip())) for address in expected_text.split(",")}
    actual = {str(ipaddress.ip_address(result[4][0])) for result in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)}
    if actual != expected:
        raise ValueError("DNS answers do not exactly match the approved VM addresses")
    print("PASS DNS matches approved addresses")
    status, headers, _ = request(domain, "/login", secure=False)
    if status not in (301, 302, 307, 308) or headers.get("location") != f"https://{domain}/login":
        raise ValueError("HTTP must redirect to the same HTTPS hostname/path")
    print("PASS HTTP-to-HTTPS redirect")
    status, _, body = request(domain, "/login")
    if status != 200 or b"<" not in body:
        raise ValueError("approved frontend /login build is not served over verified TLS")
    print("PASS TLS and real frontend entry")
    status, _, body = request(domain, "/api/v1/users/me")
    if status != 401:
        raise ValueError("real unauthenticated A05 API route must return401, not a frontend/marketing shell")
    error = json.loads(body).get("error", {})
    if error.get("code") != "UNAUTHENTICATED" or not isinstance(error.get("details"), dict) or not isinstance(error.get("retryable"), bool):
        raise ValueError("API route did not return the contract authentication error envelope")
    if not isinstance(error.get("message"), str) or not isinstance(error.get("request_id"), str):
        raise TypeError("API error required fields are missing or invalid")
    print("PASS real REST routing/authentication boundary")
    for path in ("/internal", "/internal/v1/validateAccess", "/health", "/health/live", "/health/ready", "/ws/v1/", "/api/v2"):
        status, _, body = request(domain, path)
        if status != 404 or body.strip() != b"Not found":
            raise ValueError(f"public isolation failed at {path}")
    status, _, _ = request(domain, "/unrecognized-hine-ui-route")
    if status != 404:
        raise ValueError("unknown UI route must return404, not SPA200")
    print("PASS private/health/reserved route isolation and unknown UI404")
    probe_websocket(domain)
    print("PASS exact /ws/v1 TLS WebSocket upgrade (not authenticated product E2E)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, OSError, http.client.HTTPException) as error:
        # Error descriptions are static checks/transport errors, never response bodies.
        print(f"preflight: {error}", file=sys.stderr)
        sys.exit(1)
