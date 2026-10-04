<a id="load-tests"></a>
# 負載測試

課程效能基線：50 個測試使用者／50 條 WSS、25 個一對一聊天室，每使用者平均每 5 秒發 1 則不超過 1 KiB 的文字訊息，持續 10 分鐘；另驗收一個 50 人群組，不將其流量混入基線。記錄成功率、p95、CPU／RAM；目標為送出至收件端呈現 p95 ≤2 秒，網路恢復且待補不超過 100 則時同步完成 ≤5 秒。這些是待驗證目標，未實測。

工具選 QA 熟悉的一套 HTTP＋WebSocket 工具或語言，只維護一套可重跑腳本與結果報告，不使用分散式壓力產生器。必測 W01 登入、W05 傳送、斷線後 W15／W16 同步及去重。協定負載報告與真實瀏覽器端到端驗收分開標示；收到訊框或伺服器 ACK 不等於收件端已保存／呈現。

## 候選工具與啟動命令（待 Jackie 確認）

目前提供**一套** Python 3.12+／aiohttp HTTP＋WebSocket 腳本：
[`protocol.py`](protocol.py)；固定依賴 [`requirements.txt`](requirements.txt)
（aiohttp 3.14.3，與 BA 共用版本）。這是交接候選，不代表 Jackie 已選定或核准。
不啟動假 BB、echo server、瀏覽器或產品 mock。

```sh
.venv/bin/python -m pip install -r tests/load/requirements.txt
.venv/bin/python tests/load/protocol.py --help
.venv/bin/python tests/load/protocol.py e2e --config .local/qa-users.json
.venv/bin/python tests/load/protocol.py load --config .local/qa-users.json
# 僅串接小樣本；不得標成 50 人課程基線
.venv/bin/python tests/load/protocol.py load --config .local/qa-users.json --users 2 --duration 10
# 額外第一間聊天室斷線／補送／已保存游標重播，不混入即時 p95
.venv/bin/python tests/load/protocol.py e2e --config .local/qa-users.json \
  --reconnect --state .local/qa-sync.sqlite
```

需先部署真實 BB、BA、Redis／PostgreSQL 與 TLS 私有測試入口；首輪 BA
W01–W07 可執行基本檢查，`--reconnect` 另需真實 W13–W16／BB 快照與事件流。
沒有產品端點時應失敗，不以假資料宣稱通過。不得以公開行銷首頁當聊天服務。
設定檔／環境憑證只供隔離測試帳戶，檔案必須為目前使用者擁有且禁止群組／其他人存取：

```sh
mkdir -p .local
chmod 700 .local
# 用編輯器寫入設定後：
chmod 600 .local/qa-users.json
```

設定 JSON 的 `api_base_url` 是 origin（不含 `/api/v1`），`ws_url` 必須是
`/ws/v1`。非 localhost 目標必須 HTTPS／WSS，不把憑證塞入 URL。
`users` 陣列依序兩兩配對；e2e 使用前兩個不同帳戶，load 預設需要 50 個不同帳戶：

```json
{
  "api_base_url": "https://chat-test.example",
  "ws_url": "wss://chat-test.example/ws/v1",
  "users": [
    {"login": {"email_env": "HINE_QA_A_EMAIL", "password_env": "HINE_QA_A_PASSWORD", "device_id": null}},
    {"login": {"email_env": "HINE_QA_B_EMAIL", "password_env": "HINE_QA_B_PASSWORD", "device_id": null}}
  ]
}
```

每個 user 恰好選 `login` 或 `session`。`login` 精確送 A02
`{email,password,device_id}`；`device_id` 必填，首次可 null，已有測試裝置應沿用其值。
email／password 各可用上述 `*_env`，或直接放在受保護 JSON 的同名欄位
（不得同時給兩種來源）。新隔離帳戶可另設 `register:true,display_name:"QA A"`，
先送 A01，再送 A02；A01 衝突立即失敗，不偷偷換帳戶或把衝突當成功。
已有 AccessSession 可使用：

```json
{"session": {
  "access_token": "<test access token>",
  "expires_at": "<future UTC ISO-8601>",
  "user_id": "<public user id>",
  "device_id": "<issued device id>",
  "session_generation": 1
}}
```

不刷新登入、不操作瀏覽器更新 Cookie、不解 JWT claims。權杖必須有效至測試結束；
已登入帳戶及其隔離測試資料由 BB／QA 提供。A13 以 `peer_user_id` 建立／取得
唯一一對一聊天室；不需要另外發明聯絡人／房間 fixture。

### 證據與失敗界線

- e2e 驗 W01/W02 身分與世代、W03/W04 精確 nonce／correlation；
  雙向 W05、持久 W06 和收件 W07 的 M1／原本文／event_id／order_key。
  W07 可先於 W06；ACK alone 不計成功。寄件者 W07/A19 的 C1 相符，
  收件者 W07/A19/W16 不得出現 C1。
- 沿用同一 C1／同一合法本文重試，但每次換 request event_id，必須同 M1；
  同 C1 合法不同本文需 W17 IDEMPOTENCY_CONFLICT，空本文需 INVALID_ARGUMENT。
  非文字 frame、錯誤封套／關聯、W17／關線／timeout 不計成功。
- A19 使用 `limit=50`、`before` 歷史游標讀到底，兩端逐項驗
  `(order_key,UUID bytes)` 降序、M1 唯一及 W07 的身分／本文／時間／event_id；
  同 QA intent 不得多存一筆。歷史游標絕不拿來同步。
- load 固定每使用者平均 5 秒一則、合成本文 ≤1 KiB，預設 50 WSS／25 房／600 秒。
  配對兩側錯開 2.5 秒，延誤不補發 burst。小樣本及 ws localhost 不冒充 WSS 基線。
  結束另驗 A19；不混入 50 人群組、不宣称 1k／5k／10k 容量。
  每人另列實際 dispatch offset、attempts、expected_attempts、missed_slots 和 achieved rate
  （`load_dispatch_evidence`）；完整基線每人應有 120 個時槽。
  等待傳遞結果造成送出不足時不補 burst，直接以
  `LOAD_REQUESTED_CADENCE_NOT_MET`／exit 1 失敗，不能以少送的工作量冒充基線。
  `authenticated_connections` 只統計完成有效 W02 的存活 WS／WSS，
  列 current／peak／測量窗口 initial、minimum、final；清理後 current 為 0 是正常，
  不以 socket object 存在或配置人數當已認證 WSS。完整基線窗口須持續 50 條已認證 WSS，
  非 TLS 的 50／600 設定以 `BASELINE_REQUIRES_WSS` 失敗。
- `--reconnect` 首先在 QA SQLite 原子保存完整 W14 快照和 start_cursor，
  關掉第一間房收件者 WSS，離線發一則，重連後從保存游標 W15。
  W16 每批最多 100，固定同輪 snapshot_boundary；空但前進的隱藏頁仍續讀，
  `has_more:false` 才完成。先套事件／投影再同交易保存 next_cursor，
  重播舊游標驗穩定事件與單一 M1 投影。失敗不保存不完整批次；
  SYNC_RESET_REQUIRED 明確失敗、由 QA 處理前提，不偷偷把遺失復原變成新快照。
  SQLite 只含測試投影／ID／游標，不含權杖／密碼；仍應私有保管及清理。
  W16 回條的 M1 若不在近期 W14 快照，先與游標同交易保存 pending receipt；
  後續 W07 或 A19 載入完整訊息時合併，保留 delivered→read 單調性，不遺失已讀投影。
  `protocol_recovery_ms` 在首轮同步的離線 M1 驗明後立即截止，
  刻意重播保存游標的耗時另列 `saved_cursor_replay_ms`，不混入復原目標。
- stdout 僅 JSON metrics／固定診斷 code，不含 token/password/URL/body。
  `live_receiver_protocol_p95_ms` 是**送出→收件 W07 訊框**，不是瀏覽器保存／呈現；
  復原耗時另列。`browser_persistence`／`browser_presentation` 永遠 `not_measured`。
  不送 W08/W09，避免虛構本機保存或閱讀。`baseline_requested` 與實測 `baseline_measured`
  分開；後者需要整個場景通過、逐人实际 120 次 dispatch 且窗口持续 50 已認證 WSS，
  不是只看配置 50／600 或 scheme。若需保存報告，可重導到受保護 `.local/`。
  公開 W17／REST 若包含 `auth_layer`（頂層或 details）以固定非機密診斷
  `PUBLIC_INTERNAL_METADATA_LEAK` 失敗，不回顯內部值。
- `--monitor-pid <actual-local-product-pid>` 透過 Linux `/proc` 量單一產品程序 CPU／RSS，
  缺 PID 就標 `not_supplied`，不可用就標 `unavailable`，不填假值；
  CPU 百分比以單核心 100% 為單位，多核心可超過 100%，RSS 不是整台 VM 記憶體。
  VM／資料集／網路／真實瀏覽器結果仍需 QA 另行記錄。
- exit 0：所選協定場景通過；exit 1：協定／產品端點／timeout 失敗；
  exit 2：CLI／設定／本機輸入前提失敗；中斷 130。`--help` 不連服務。
  永久 oracle 行為測試（沒有 fake server／產品 mock）：

```sh
.venv/bin/python -m unittest discover -s tests/e2e -p 'test_protocol_tool.py'
```

目前尚未對真實 BB 執行二帳戶 E2E 或 50 人基線；上述皆為可重跑工具與待驗前提，
不是量測／核准紀錄。瀏覽器驗收見 [`../e2e/README.md`](../e2e/README.md)。

## 未來壓測（非本版交付）

1,000／5,000／10,000 條連線僅作未來負載測試，不是本版課程基線或必交容量。
