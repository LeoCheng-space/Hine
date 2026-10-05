<a id="realtime-service"></a>
# 即時服務 — 訊息、回條與同步

Python 3.12+ / aiohttp / redis-py implementation of **W01–W17 and W19**.
W11/W12/W20 group projections use the existing committed-notice boundary.
BB remains the sole JWT, session, authorization, canonical Unicode-length,
product-quota and PostgreSQL persistence authority. There is no local JWT,
database, credential or persistence fallback. W18 contact notifications,
activity leases and push are not implemented; unsupported client commands
return `INVALID_ARGUMENT`.
The existing internal committed-notice boundary accepts authenticated BB
session invalidations and A14–A18 projections without taking over BB group APIs.

## Run locally

From the repository root, with a real Redis service and an actual BB internal
HTTP service:

```sh
python3.12 -m pip install -r backend/realtime/requirements.txt
export PYTHONPATH=backend/realtime/src
export HINE_ENV=development
export REALTIME_HOST=127.0.0.1 REALTIME_PORT=8081
export API_INTERNAL_URL=http://127.0.0.1:8080
export REDIS_URL_SECRET_REF=/absolute/path/to/redis_url
export INTERNAL_CALLER_TOKEN_SECRET_REF=/absolute/path/to/realtime_internal_token
export INTERNAL_ALLOWED_CALLERS='{"api":"/absolute/path/to/api_internal_token"}'
export HEARTBEAT_INTERVAL_SECONDS=30 HEARTBEAT_TIMEOUT_SECONDS=90
export SYNC_PAGE_LIMIT=100
export INVALIDATION_POLL_SECONDS=5 INVALIDATION_STALE_SECONDS=15
export NOTICE_CATCHUP_HOLD_MS=1000
python3.12 -m hine_realtime
```

The secret files contain the actual Redis URI and **different** service bearer
credentials, with at most a trailing line ending. Keep them outside Git and
readable only by the appropriate owner. `REDIS_URL` is also accepted for local
development; the secret-file setting takes precedence and avoids environment
URI exposure. Redis URIs support `redis://` and `rediss://`, without query options.
BA does not receive a JWT signing key. Container builds use only
`backend/realtime` as their context:

```sh
docker build -t hine-realtime -f backend/realtime/Dockerfile backend/realtime
```

Compose has an optional `realtime` profile, not a placeholder BB image.
Missing BB means the module cannot be ready or authenticate users. File-backed
Compose secrets retain the host owner/mode: the configured container UID/GID
must be able to read them even with all capabilities dropped. The deployment
scripts document owner provisioning. Port 8081 is private; expose only exact
`/ws/v1` through the HTTPS/WSS proxy, never `/internal/*` or `/health/*`.
Local HTTP/WS testing is not a production TLS deployment.

## Routes and settings

| Route | Behavior |
|---|---|
| `GET /ws/v1` | Client W01 first; no same-connection reauthentication. W03→W04, W05→confirmed W06 plus Redis W07, correlated W17 errors. |
| `POST /internal/v1/publishCommitted` | `{"notice":RealtimeNotice}`; only the authenticated `api` credential, only session invalidations or A14–A18 sources. |
| `POST /internal/v1/getDevicePresence` | `{"subject_id":string,"device_id":string}`; actual local valid connections, `unknown` when Redis cannot be checked; `activity:"unknown",valid_until:null`. |
| `GET /health/live` | Always 200 when the process is serving; dependencies both `not_checked`. |
| `GET /health/ready` | 200 only after a current real Redis PING, active subscription, BB invalidation catchup and fresh authority; otherwise 503. BA PostgreSQL is always `not_checked`, not a fabricated DB check. |

Required BA configuration: `HINE_ENV`, `API_INTERNAL_URL`, Redis URI/secret
reference, outbound token secret reference, allowed-caller JSON map and the
five heartbeat/invalidation variables above, plus `SYNC_PAGE_LIMIT`. Missing/invalid core settings
leave the process live but unready (`CONFIG_MISSING`) and reject authentication.
Invalidation poll must be shorter than freshness, freshness may not exceed
15 seconds, and notice hold may not exceed 1000 ms. Defaults for listener are
`REALTIME_HOST=0.0.0.0`, `REALTIME_PORT=8081`.

Operational transport defenses (not BB's W05 product 5/s, burst10 quota):

| Setting | Default |
|---|---:|
| `REALTIME_MAX_FRAME_BYTES` | 65536 |
| `REALTIME_MAX_OUTGOING_FRAMES` | 128 per connection |
| `REALTIME_MAX_OUTGOING_BYTES` | 1048576 per connection |
| `REALTIME_MAX_CONNECTIONS` | 1000, including reserved handshakes |
| `REALTIME_MAX_GROUP_REMOVALS` | 4096 per connection |
| `REALTIME_FRAME_RATE` / `REALTIME_FRAME_BURST` | 120 frames/s / 240 per connection |
| `REALTIME_REDIS_PREFIX` | `hine:realtime` |

These resource settings do not add public fields or canonical text/EntityID
limits, and are not measured capacity claims. Incoming JSON disallows duplicate
keys/non-JSON numbers, validates required/null/type/UUID/union fields and never
normalizes text or nonce. W03's nonempty nonce is echoed byte-for-byte as a
string, with the same connection's request correlation; replay does not extend
heartbeat lifetime. Unauthenticated sockets have a 10-second admission deadline;
only valid W03 advances heartbeat lifetime. BB HTTP and socket writes have
2-second deadlines. Slow output is bounded and closes only that connection;
authority-stale data is discarded without logging out the user.

## Persistence, fanout and invalidation guarantees

- W05 goes directly to `persistIfAbsent`, with BB-validated subject/device/
  session/generation and the unmodified intent. There is no premature
  `authorize(send)` or second message quota. W06 requires every documented
  committed result field, including `status:"persisted"`, UUIDs, stable
  `order_key`, timestamp, recipients, invalidation position and nullable
  membership version. Malformed write success is `OUTCOME_UNCONFIRMED`, never ACK.
- The contract names `created|existing_same` without specifying a JSON
  discriminator field. Both outcomes use the same documented persisted fields;
  BA does not invent a discriminator or another wire envelope.
- W07 uses BB's stable event/message IDs, timestamp, ordering and committed
  recipients, and the trusted public sender mapping. C1 is included only for
  the sender's own devices. Per-connection `authorize(receive)` for W07 uses
  `resource_type:"message"` and the actual M1, so BB's current join boundary
  protects delayed messages even when A18 was lost and the user rejoined.
  Other group control projections retain conversation-resource checks;
  recipients are never derived from those checks. Own minimal W12 is the
  explicit authorization exception.
- Redis PUBLISH and the completion fingerprint are one Lua operation.
  Failed/denied PUBLISH does not mark a notice done; successful duplicate
  notice IDs do not republish, and changed content for the same ID is rejected.
  Completion keys store only UUID/hash metadata (not message bodies or C1) and
  do not silently expire. Redis loss/flush loses this optimization; client
  stable-event deduplication and BB history/feed are still necessary.
  A confirmed BB commit still permits W06 when Redis fanout fails. Publishing
  success never means delivery, revocation completion or product persistence.
- BB invalidation polling starts before W01 can succeed. Applied positions
  advance only contiguously. Out-of-order records may revoke early; final
  W01 check+registration shares the same lock with application, including
  newer known records and historical coverage if local retention advanced.
  Freshness uses the monotonic **start of the last complete catchup**, never
  receipt time or clocks compared between machines.
- A notice's newer position must catch up within 1000 ms or its live fanout
  is abandoned. Every queued frame rechecks validity, token expiry and node
  freshness when starting its socket write. Session invalidation clears unsent
  data; refresh affects only older generations of that session, logout/
  replacement only that session, not other devices.
- Every authenticated, structurally valid A18 notice applies its removed
  member/conversation/version to that member's existing connections immediately,
  before notice catchup or output waits. This includes split fragments sent only
  to remaining members. Pending output retains its membership version and M1;
  the last socket-write check rejects older/equal-version content even after
  rejoin or a previously allowed BB response. Own minimal W12 remains deliverable,
  later higher-version membership/data is eligible, and unrelated conversations
  and sessions are not revoked. Removal versions only increase and are retained
  for the connection lifetime; they are never silently expired/evicted.
  Exhausting the configured metadata capacity invokes existing resource cleanup
  for that connection rather than forgetting an active exclusion. This is a
  resource-pressure reconnect, not a group-removal logout.
- `CURSOR_INVALID` closes every local connection before resetting to BB's
  current head. Stale authority preserves W04/W17 control traffic but no data
  or new W01 success. Token expiry and heartbeat timeout close transport even
  when BB is unavailable. Reconnection creates a new authenticated connection.
- Only trusted HINE `UNAUTHENTICATED` with `details.auth_layer:"user_session"`
  closes the operation's user connection. Service identity/missing-layer/
  non-HINE failures become `DEPENDENCY_UNAVAILABLE`, not account logout.
  Other BB error codes and retryability survive; only a known safe nonnegative
  integer delay is forwarded for retryable rate limiting. Public errors and
  logs do not copy BB messages/details, tokens, private subject IDs or text.

## Tests and handoff

With an **isolated real Redis**, run from the repository root:

```sh
python3.12 -m pip install -r backend/realtime/requirements-dev.txt
HINE_TEST_REDIS_URL=redis://127.0.0.1:6397/0 \
  PYTHONPATH=backend/realtime/src \
  python3.12 -m unittest discover -s tests/integration -p 'test_realtime*.py'
```

`tests/integration/test_realtime_boundaries.py` starts actual aiohttp HTTP/WS
servers and uses actual Redis Pub/Sub. Its BB authority is **test-only**, stateful
and isolated from production: it controls canonical/C1/commit barriers, session
records and fault responses to exercise consumer risks. It is **not product
E2E**, does not provide a production BB/JWT/PostgreSQL fallback, and does not
prove A19, browser persistence/presentation, production TLS or measured latency.
Redis-required tests skip only when no explicit test target was supplied and
the prerequisite is unavailable; an unavailable explicit `HINE_TEST_REDIS_URL`
fails verification. Neither is acceptance success. One isolated test creates
a temporary Redis ACL user to prove failed PUBLISH can be retried.

The tests guard against premature ACK, public/private identity confusion,
receiver C1 leaks, replay/duplicates, canonical/quota precedence delegation,
malformed committed results, service/user credential confusion, bad notice
source mapping, lost/out-of-order invalidation, admission races, stale delivery,
expiry, per-frame authorization and bounded recipient output. Stateful group
regressions capture an allowed pre-removal authorization response, hold the real
socket writer lock, apply fragmented A18 notices, and verify no old body escapes
while minimal W12, rejoin data and unrelated conversation traffic still work.
They also verify message readability after a lost A18/rejoin, immediate removal
during a notice catchup hold, and fail-closed metadata pressure.

Real integration still requires BB's actual implementations of
`validateAccess`, `persistIfAbsent`, `authorize` and
`readSessionInvalidations`, with the exact shared REST/error envelopes, caller
secret validation, trusted public mapping, atomic PostgreSQL commit/C1/feed,
quota/canonical precedence and transactional invalidation positions. BB must
send only committed, canonically valid, structurally correct notices. Actual
`persistReceipt`, `readBootstrap` and `readFeed` are also required for receipt
and synchronization paths. Actual BB/FA/FB artifacts and A19 remain required
for product acceptance; test-only authority and QA projection storage do not
prove PostgreSQL/JWT or browser persistence/presentation.

BA-specific causes, effects, detection, degradation, recovery and release gates
are documented in the [failure analysis](../../docs/testing/backend-a-failure-analysis.md).
The [local fault drill](../../tests/faults/README.md) kills/restarts only owned BA
and Redis children and cuts an isolated BB test link; its component evidence is
not production PostgreSQL/JWT durability, browser acceptance, VM recovery or an SLO.

Dependency pins were selected from current [aiohttp PyPI metadata](https://pypi.org/pypi/aiohttp/json)
and [redis PyPI metadata](https://pypi.org/pypi/redis/json); runtime API references:
[aiohttp server](https://docs.aiohttp.org/en/stable/web_reference.html),
[redis asyncio](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html).

## Receipt and synchronization delivery

- W08/W09 carry only the declared message ID and conversation. BA forwards the
  trusted session binding to BB and sends correlated W19 only for a complete
  confirmed receipt result. `read` cannot regress when a later W08 arrives.
  W10 is a direct-only projection using BB's stable status event, time, state,
  observers, and the trusted public recipient. A failed Redis fanout cannot
  undo a confirmed W19. Group individual receipts still get W19, never an
  aggregate W10.
- W13 preserves the opaque snapshot/page pair; W15 preserves the original
  cursor and optional fixed boundary. BA does not install H, save client
  cursors, compare opaque cursor strings, or silently rewrite a partial
  response. Public W14/W16 structures, complete snapshots, sender-only C1 and
  configured page limits are validated before delivery.
- `SYNC_PAGE_LIMIT` is now required, a positive integer no greater than100;
  the shared course configuration remains100. W14 counts conversations plus
  recent messages as logical items; W16 limits returned events. BB remains
  responsible for its1000-position scan cap and current page authorization.
- Public read results have no internal watermark field. BA completes a new
  session-invalidation catchup after every read, then revalidates deduplicated
  current message/history permissions within one bounded authorization window.
  Queue delivery rechecks expiry/freshness and request-start A18 revisions after
  permission/socket-lock waits. A tainted whole response becomes a correlated
  error without cursor progress; retrying the same cursor can obtain BB's
  current authorized data, including other conversations and minimal own W12.
- The real HTTP/WS/Redis regression suite and actual CLI reconnect smoke use a
  stateful test-only authority. They are not real BB/JWT/PostgreSQL/browser,
  deployment or50-WSS acceptance. Existing QA's `--reconnect --state` exercises
  offline recovery, atomic QA projection/cursor persistence and stable replay.
