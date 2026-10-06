# Product and Backend A fault drills
 
## Real PostgreSQL product acceptance

[`product_fault_drill.py`](product_fault_drill.py) runs the real API and BA
modules, actual SQL migrations, private SCRAM-authenticated PostgreSQL 17,
authenticated Redis, and Caddy HTTPS/WSS with a verified owned private CA.
It never uses the test-only authority described below. Run as a non-root Linux
user with Python 3.12+, both backend requirements installed, and native tools:

```sh
.venv/bin/python tests/faults/product_fault_drill.py \
  --postgres-bin /operator/path/postgresql-17/bin \
  --redis-server /operator/path/redis-server \
  --caddy /operator/path/caddy \
  --python /absolute/path/to/.venv/bin/python \
  --output /protected/existing-directory/new-product-faults.json \
  --web-root /absolute/path/to/frontend/app/dist
```

`--web-root` is optional; it must refer to an existing real build, not a sample
shell. All other arguments shown are required. `--case PF03` may be repeated
to select cases; omitted selects all eight. Unselected cases stay
`NOT_EXERCISED`. Each case owns a fresh cluster, random ports, private files
and process groups; listener attestation prevents accepting an unrelated
service. Cleanup only signals recorded children, including cancellation.
No operator PostgreSQL/Redis, Docker, SSH, global firewall or cloud write is used.

| Case | Actual fault and observed invariants |
| --- | --- |
| PF01 | API SIGKILL; unchanged SQL records, existing JWT/public identity, saved cursor and original C1/M1 recovery. |
| PF02 | BA SIGKILL; offline message recovered from saved cursor, stable event and original C1. |
| PF03 | Native PostgreSQL stop/restart; live200/ready503, new W01 rejected, no fake ACK/data; after the real stale window existing sockets retain exact W04 and dependency W17 only; same sockets recover. Independent real 30-second API-issued/SQL-persisted token expiry closes stale sockets. |
| PF04 | Native Redis reset; unknown presence, API still ready, confirmed PostgreSQL ACK without live fanout, durable feed recovery. |
| PF05 | Drop actual committed A04 notification; durable invalidation rejects revoked JWT and closes its WSS, other device continues. |
| PF06 | Drop the actual committed API write response; unknown outcome/no false ACK, same original C1 returns one SQL M1 mapping. |
| PF07 | Owned SQL trigger forces a real transaction rollback; no message/C1 mapping or ACK; remove trigger and retry successfully. |
| PF08 | Stop writers, prove zero source/clone sessions, real pg_dump and single-transaction pg_restore to a new owned clone; exact archived table records, JWT/public IDs, revoked session, history, receipt, feed and C1 survive. |

Output is sanitized booleans/counts/monotonic timings/source hashes, never
credentials, body, IDs, cursors or raw private logs. A new0600 JSON is published
atomically with no-clobber and fsync; existing output including symlinks is
refused before launching. Exit0 means all selected cases passed,1 means an
observed case failed/interrupted,2 means input/prerequisite failure. The full run
retains failed and subsequent observed case results rather than fabricating PASS.
Execution evidence is linked from the [acceptance matrix](../../docs/testing/acceptance-matrix.md).

This proves only the named **local native product** experiments. It does not
certify public VM/TLS, GCS physical bytes, browser IndexedDB/rendering, disk loss,
HA, RTO/RPO, a statistical SLO or a universal 15-second delivery boundary.
The archived set has no post-backup acknowledged writes; it is not an RPO claim.

## Historical Backend A local-component drill

`ba_fault_drill.py` exercises **native BA and Redis processes, actual HTTP/WS
clients, and an owned loopback forwarding socket**. Its BB endpoint subclasses
`tests/integration/receipt_sync_support.py::AddonAuthority`: a continuously alive,
stateful **test-only in-memory authority**. It is neither production BB nor a
PostgreSQL/JWT implementation, and is never imported by production runtime.

These drills supplement the [BA failure analysis](../../docs/testing/backend-a-failure-analysis.md).
A runner existing in the repository is not execution evidence. Only a newly
produced JSON with six observed `PASS` records establishes this local-component
run; historical integration-test results remain separate.

## Prerequisites and entry command

- Linux with accessible `/proc` ownership metadata, POSIX signals and Python 3.12 or newer.
- `aiohttp` and `redis` installed in both the runner interpreter and the optional
  BA child interpreter, using `backend/realtime/requirements.txt` versions.
- An executable **native** `redis-server`; no Docker, root, operator Redis,
  `.env`, product credentials, SSH or cloud resource is used.
- A source checkout containing BA and the two existing integration fixture
  modules. Source roots are resolved from the runner location, not an inherited
  `PYTHONPATH` or the working directory.
- A writable **new** output path whose parent directory already exists. Existing
  output paths, including symlinks, are rejected rather than overwritten.

Run from the checkout root, substituting your native Redis path:

```sh
.venv/bin/python tests/faults/ba_fault_drill.py \
  --redis-server /operator/path/redis-server \
  --python .venv/bin/python \
  --output /tmp/backend-a-local-faults-new.json
```

For the locally supplied native binary and its shared libraries:

```sh
LD_LIBRARY_PATH=/tmp/hine-tools/root/usr/lib/x86_64-linux-gnu \
  .venv/bin/python tests/faults/ba_fault_drill.py \
  --redis-server /tmp/hine-tools/root/usr/bin/redis-server \
  --python .venv/bin/python \
  --output /tmp/backend-a-local-faults-new.json
```

`--redis-server` and `--output` are required; `--python` defaults to the runner's
interpreter. The BA command is actually `--python -m hine_realtime`, with the
checkout's `backend/realtime/src` configured as its source root. No BA application
is created in the runner process.

The runner uses standard poll **5 s**, stale **15 s**, notice catchup hold
**1000 ms**, heartbeat **30/90 s**, and sync page limit **100** settings. DR-03
and DR-04 each wait a real 16-second stale window; they do not edit private clocks
or shorten freshness configuration. The six cases normally fit within minutes,
but that is an operating expectation, not a measured result or SLO. Each case
has a 75-second execution deadline; finally-cleanup can extend that deadline to
reap the runner's own children.

Exit codes:

| Code | Meaning | Evidence |
| --- | --- | --- |
| `0` | All six cases observed and all checks passed | Run and all scenarios `PASS` |
| `1` | Actual case, observation, cleanup, timeout or interruption failed | Active case `FAIL`; later cases `NOT_EXERCISED`; completed earlier results retained |
| `2` | Input/prerequisite failure before case execution | All scenarios `NOT_EXERCISED`, never `PASS` |

If no output can be created, there can be no JSON: a fixed error category is
printed and exit code is `2`. The existing destination is never replaced.
Otherwise a private `0600` temporary file on the output filesystem receives the
sanitized report, including prerequisite failure or handled SIGINT. After close
and fsync it is atomically hard-linked to the new destination without replacing
an existing path. The final path never exposes empty or partially written JSON.
The runner stops after the first failed case rather than inventing later results.
Run it again only with a different new output path.

## Scenario bindings and observations

Each case gets fresh components. Within its failures and recovery the same test
BB authority remains alive, which is verified by a direct HTTP health response.
The fault is always scoped to a process/socket owned by that case.

| ID and name | Injection | Required observed behavior |
| --- | --- | --- |
| **DR-01 `BA_SIGKILL_RECOVERY`** | `SIGKILL` of the actual BA child after a confirmed test-memory write, with receiver offline | Child exit signal and old WS closure; new BA child and fresh W01/W02; **saved** sender/receiver cursors recover the original M1/event; sender sees original C1, receiver does not; original C1 retry returns original M1 with one test-memory write. Ready recovery and authenticated client sync are separately timed. |
| **DR-02 `REDIS_STOP_RESTART`** | Stop the owned Redis process, then restart it on the same isolated port with RDB/AOF disabled | Ready HTTP `503`, presence `unknown`; real W05 still gets confirmed W06 despite missing live fanout; restored native PING/subscription/readiness and presence; ephemeral marker loss; saved-cursor sync recovers missing M1; original C1 retry adds no write. **No Redis message-durability claim.** |
| **DR-03 `BB_LINK_OUTAGE`** | Close the owned forwarding listener **and existing keepalive transports**, retaining the authority process | TCP connection refused; new W01 gets dependency error and no W02; established W05 gets dependency error and no fake ACK/write; after the real standard stale window heartbeat still works but sync/data fail without cursor output; restored listener/full catchup lets the **same** valid sessions continue and saved cursor sync recover a confirmed message. |
| **DR-04 `LOST_LOGOUT_BB_OUTAGE`** | Close forwarding link; commit a test `SessionInvalidation` entry without publishing its notification | After a real stale window, old binding cannot write/sync; direct authority remains alive; restore/catchup closes only that revoked binding, not the other device of the same user or receiver; the other device still heartbeats and commits a message. Commit-to-probe/closure timing uses actual monotonic timestamps, not a production PostgreSQL transaction bound. |
| **DR-05 `C13_SERVICE_CREDENTIAL_FAILURE`** | Actual inbound service credential requests plus actual BB HTTP `401 service_identity`, then scoped `401 user_session` responses | Wrong inbound credential and outbound-as-inbound credential rejected HTTP `401`; correct inbound credential works; established user gets dependency error but session/heartbeat survive outbound service failure; new W01 has no W02; service recovery preserves established binding. Explicit user-session HTTP failure instead closes only that binding; other device still operates. Private auth layer/body is not echoed in WS errors or evidence. |
| **DR-06 `UNCERTAIN_WRITE_AND_ACK_RECOVERY`** | Drop the real confirmed BB write response by aborting its forwarding connection; separately hold another confirmed response while the actual client WS disconnects; inject a structured known-rollback error | First write returns `OUTCOME_UNCONFIRMED`, never false W06; saved-cursor sync and **original C1** recover original M1/event with one write. Second intent is confirmed in test memory, but disconnected client receives no W06; reconnect, saved-cursor sync and original-C1 retry recover that second M1 without duplicate writes. Structured `PERSISTENCE_FAILED` is distinguished from uncertain transport outcome and does not commit or ACK. |

The ACK-loss subcase immediately aborts the owned client transport after a real
test-authority commit, then verifies that the held BB `200` response was fully
forwarded before reconnecting. It does not wait for a circular WebSocket close
handshake or claim a captured ACK packet was dropped downstream. The uncertain
case drops an actual BB `200`, rather than returning a fake success or patching BA.
The known-rollback comparison is explicitly an HTTP fixture error, not a real
PostgreSQL rollback experiment.

No scenario is a bare “did not throw” or echo-server check: it asserts actual
client HTTP status/WS frames, correlated ACK absence/presence, closure, recovered
message/event/C1 equality or privacy, cursor progress, and fixture intent counts.
Only comparison **booleans/counts** leave the runner; the values compared do not.

## Evidence schema and interpretation

The single JSON document has `schema_version: 1` and these fields:

- `run_id`: evidence UUID (not a session/message/device ID).
- `started_utc`, `completed_utc`, `status`, `exit_code`.
- `scope: LOCAL_COMPONENT_WITH_TEST_BB`.
- `configuration`: explicit settings and `redis_persistence_enabled: false`.
- `provenance.analysis_baseline`: analysis reference commit;
  `provenance.git_head`: actual checkout HEAD observed at execution;
  `provenance.source_sha256`: actual relative-path SHA-256 digests of BA Python
  source, the two fixture modules, runner, README and runtime requirements. HEAD
  alone does not imply a clean working tree; source hashes bind the actual files.
- `environment`: OS/release/architecture, actual runner and child Python,
  aiohttp/redis-py versions, and parsed native Redis version.
- `limits`, `unmeasured`: fixed scope categories. Real BB/PostgreSQL/JWT,
  VM/disk/host failure, browser/IndexedDB C1, HA, 50-WSS load and empirical
  occurrence/RPN/RTO/RPO/SLO are **not measured** by this drill.
- `scenarios`: ordered records with exact IDs `DR-01` through `DR-06`, `name`,
  `status` (`PASS`, `FAIL`, `NOT_EXERCISED`), `fault_kind` (`actualprocess`,
  `actualsocket`, `HTTPfixturefault`), `checks`, `timings_ms`, `limits`, and on
  failure a runner-authored fixed `failure_code`.

`checks` contains actual booleans/counts/HTTP statuses, never copied private
response strings. `timings_ms` contains elapsed `time.monotonic()` measurements
for the named event intervals, including setup/cleanup for overall scenario
elapsed. An empty unexercised record is not a zero-duration successful recovery.
A single elapsed measurement is **not** p95, RTO, a guaranteed 15-second
production revocation bound, an occurrence rate, or an SLO result.

The normal terminal output is only `BA_FAULT_DRILL_PASS`, `BA_FAULT_DRILL_FAIL`,
or `BA_FAULT_DRILL_NOT_EXERCISED`; diagnostics use fixed categories. Request IDs,
ports, URLs, usernames, tokens, session/device/message/event/C1 identifiers,
cursors, message bodies, private auth details and log contents are not serialized.
Source paths are repository-relative. After review, the parent can copy sanitized
execution evidence to the analysis' evidence location; this runner never updates
repository evidence or a historical result automatically.

## Resource ownership and safety

- Fresh `0700` temporary directory, random Redis prefix and ephemeral loopback
  ports for every case; no connection to a configured/operator Redis instance.
- Redis config, URL, service secret files and private child logs are `0600`.
  Redis is password-protected with a fresh test password, has only loopback TCP
  plus a private Unix socket, and runs foreground with RDB/AOF disabled. Runner
  readiness/probes use the private Unix socket and verify its child PID through
  native Redis INFO before starting BA, avoiding accidental attachment during a
  TCP-port reservation race. BA uses the owned Redis's isolated TCP endpoint.
- Before BA HTTP readiness probes, the runner matches its child's file-descriptor
  socket inode to the exact loopback LISTEN entry in that child's `/proc/net/tcp`.
  A port collision cannot be accepted merely because an unrelated service says ready.
- Inherited product configuration/secrets are excluded from the BA environment.
  No real accounts/passwords are read; the existing fixture's synthetic tokens
  are test data. The optional `LD_LIBRARY_PATH` supports the native binary.
- Child stdout/stderr stay in private files and are removed with the temporary
  directory. Framework logging is disabled so private request diagnostics cannot
  reach the terminal or public JSON.
- Finally-cleanup closes peers/listeners/HTTP clients and signals/waits only
  recorded child handles. A stop escalates to SIGKILL only for that owned child.
  Cleanup stays shielded through multiple independent timeout/SIGINT cancellations
  and propagates cancellation only after owned cleanup finishes. No `killall`,
  operator PID lookup, global
  network fault, filesystem/VM damage, Docker, root or cloud API is used.

## External validation gates

These local cases do not measure real BB PostgreSQL commit/rollback durability,
real JWT/key rotation, cross-service deployment latency, VM/disk loss, external
Redis/DB failure domains, browser persistence, HA or load acceptance. Their
component observations do not change the committed BA feature scope or rewrite
historical test counts. Use the linked failure analysis' real-BB/VM procedures
with provisioned disposable deployment resources and approval for those separate
gates; do not relabel this fixture run as product E2E/deployment acceptance.
