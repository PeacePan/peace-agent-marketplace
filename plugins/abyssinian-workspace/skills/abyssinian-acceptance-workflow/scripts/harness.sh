#!/usr/bin/env bash
# Abyssinian 本機驗收環境的啟停腳本：內嵌資料庫＋Server（npm run dev）＋Worker（npm run worker:dev）＋假中台，全部只在本機、不碰共用 dev。
#
# 用法（在 Abyssinian/ 目錄執行，或用 ABY_DIR 指到它）：
#   bash <本腳本> prepare            檢查埠、產生假中台檔案、寫 .env（已有 .env 就拒絕）
#   bash <本腳本> up                 prepare 之後依序啟動假中台、Server（含內嵌資料庫）、Worker，等到第一輪資料集發佈
#   bash <本腳本> status             各行程是否存活、各埠是否在聽、Server 就緒檢查
#   bash <本腳本> upsert <表名> '<表頭 JSON>' ['<表身 JSON>']   對假中台新增或更新一筆（日期用 {"$date":"ISO"}）
#   bash <本腳本> down               只用 PID 檔停止自己啟動的行程，確認埠釋放
#   bash <本腳本> clean              down 之後移除本腳本產生的 .env、.dev-db、.local-data
#
# 環境變數：ABY_DIR、ABY_DB_PORT（54391）、ABY_SERVER_PORT（3191）、ABY_FAKE_PORT（3192）、ABY_CONTROL_PORT（3193）。
# 埠被別人占用時一律停止並回報占用者，不自行結束它、不自行換埠。

SKILL_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABY_DIR="${ABY_DIR:-$PWD}"
DB_PORT="${ABY_DB_PORT:-54391}"
SERVER_PORT="${ABY_SERVER_PORT:-3191}"
FAKE_PORT="${ABY_FAKE_PORT:-3192}"
CONTROL_PORT="${ABY_CONTROL_PORT:-3193}"
WORK_DIR="$ABY_DIR/.local-data/accept"
RUN_DIR="$WORK_DIR/run"

fail() { echo "錯誤：$1" >&2; exit "${2:-1}"; }

# 確認目前在 Abyssinian 專案目錄
check_project() {
  [ -f "$ABY_DIR/package.json" ] && grep -q '"name": "abyssinian"' "$ABY_DIR/package.json" || fail "ABY_DIR（${ABY_DIR}）不是 Abyssinian 專案目錄，請先 cd 進 Abyssinian/ 或設定 ABY_DIR" 2
  [ -d "$ABY_DIR/node_modules" ] || fail "沒有 node_modules：請先 npm ci，或從別的 worktree 用 cp -cR 複製（前提是 package-lock.json 相同）" 2
}

# 印出某個埠的占用者（pid、指令、cwd、已執行時間），沒有占用者回傳 1
port_owner() {
  local pids pid
  pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | sort -u)"
  [ -n "$pids" ] || return 1
  for pid in $pids; do
    echo "  埠 $1：pid=$pid 指令=$(ps -p "$pid" -o command= | cut -c1-100) cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p') 已執行=$(ps -p "$pid" -o etime= | tr -d ' ')"
  done
  return 0
}

# 讀 PID 檔並判斷行程是否存活
pid_alive() {
  local f="$RUN_DIR/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null
}

# 埠有人在聽就停止，並印出占用者；用來避免蓋到別的 session 的環境
require_ports_free() {
  local busy=0 p
  for p in "$DB_PORT" "$SERVER_PORT" "$FAKE_PORT" "$CONTROL_PORT"; do
    if port_owner "$p" >/dev/null; then busy=1; port_owner "$p" >&2; fi
  done
  [ "$busy" = 0 ] || fail "上列埠已被占用。不要結束它（可能是別的 session 或使用者自己的環境）：確認它不屬於本次驗收後，改用 ABY_*_PORT 換一組埠，或請使用者處理" 3
}

ENV_MARK="由 abyssinian-acceptance-workflow 的 harness.sh 產生"

write_env() {
  # 只覆蓋自己上次寫的 .env（第一行有標記）；別人的 .env 可能含有別的設定，不動
  if [ -f "$ABY_DIR/.env" ] && [ "${ABY_FORCE_ENV:-0}" != 1 ] && ! head -n 1 "$ABY_DIR/.env" | grep -q "$ENV_MARK"; then
    fail "已有不是本腳本產生的 .env：不覆蓋（可能含有別的設定）。確認可丟棄後以 ABY_FORCE_ENV=1 重跑，或先備份" 4
  fi
  cat > "$ABY_DIR/.env" <<EOF
# ${ENV_MARK}；全是本機假值
APP_ENV=development
DB_HOST=127.0.0.1
DB_PORT=$DB_PORT
DB_USERNAME=postgres
DB_PASSWORD=postgres
DB_NAME=abyssinian
DB_SSL=false
PORT=$SERVER_PORT
ADMIN_IDENTITY_MODE=open
DEVICE_TOKEN_SECRET=local-dev-only-secret-at-least-32-characters-long
JAVACAT_BASE_URL=http://127.0.0.1:$FAKE_PORT/graphql-pos
JAVACAT_ACCESS_KEY_ID=accept-key
JAVACAT_SECRET_ACCESS_KEY=accept-secret-value
# 縮短讀取與編譯節奏，讓驗收不必等幾十分鐘（正式預設分別是 300／60／300／1800 秒）
SOURCE_AVOID_WINDOWS=
SOURCE_READ_INTERVAL_SECONDS=30
SOURCE_SCHEDULER_TICK_SECONDS=5
DATASET_COMPILE_INTERVAL_SECONDS=5
DATASET_QUIET_SECONDS=10
DATASET_MAX_WAIT_SECONDS=60
DATASET_NOTIFY_SPREAD_SECONDS=0
DATASET_RETRY_AFTER_SECONDS=1
EOF
}

cmd_prepare() {
  check_project
  require_ports_free
  mkdir -p "$RUN_DIR"
  # 假中台：由 repo 現行的 fake-javacat.ts 套 patch 產生，原檔改了而 patch 套不上時明確失敗，不使用過期的複本
  local orig="$ABY_DIR/test/integration/support/fake-javacat.ts"
  [ -f "$orig" ] || fail "找不到 ${orig}：這個版本沒有假中台，請改用別的資料來源（見 references/local-harness.md）" 5
  cp "$orig" "$WORK_DIR/fake-javacat-multi.mts"
  patch -s "$WORK_DIR/fake-javacat-multi.mts" < "$SKILL_SCRIPTS_DIR/fake-javacat-multi.patch" || fail "fake-javacat.ts 已改動，fake-javacat-multi.patch 套不上：請依原檔重新產生 patch（改兩處：startFakeJavaCat 加 port 參數、sessionCookie 改成集合）" 5
  cp "$SKILL_SCRIPTS_DIR/fake-world.mts" "$SKILL_SCRIPTS_DIR/device-peek.mts" "$WORK_DIR/"
  write_env
  echo "prepare 完成：${WORK_DIR}（埠 資料庫=$DB_PORT Server=$SERVER_PORT 假中台=$FAKE_PORT 控制=${CONTROL_PORT}）"
}

# 等某個條件成立（最多 $1 秒），條件是後面的指令
wait_until() {
  local limit="$1" waited=0
  shift
  while ! "$@" >/dev/null 2>&1; do
    [ "$waited" -lt "$limit" ] || return 1
    sleep 2
    waited=$((waited + 2))
  done
}

# 啟動一個背景行程並記下 PID：$1 名稱，其餘是指令
launch() {
  local name="$1"
  shift
  cd "$ABY_DIR" || return 1
  # &、$! 必須接在同一個簡單指令後面，PID 才是實際行程（接在 cd && 後面會變成子殼的 PID）
  nohup "$@" > "$RUN_DIR/$name.log" 2>&1 &
  echo $! > "$RUN_DIR/$name.pid"
}

cmd_up() {
  # 殘留的資料庫與物件儲存帶著上次的來源快取與版本，而假中台每次啟動都重新灌種子：兩邊不一致。
  # 增量讀取只看 _updatedAt 之後的變動，看不出「被還原的值」與刪除，要等每日全量校驗才會對齊，驗收結果會悄悄失真。
  if { [ -d "$ABY_DIR/.dev-db" ] || [ -d "$ABY_DIR/.local-data/objects" ]; } && [ "${ABY_KEEP_DATA:-0}" != 1 ]; then
    fail "發現上次留下的 .dev-db 或 .local-data/objects：資料庫與假中台的種子會不一致。請先執行 clean 從乾淨狀態開始（只有確定要保留資料時才用 ABY_KEEP_DATA=1）" 8
  fi
  cmd_prepare || exit $?
  cd "$ABY_DIR" || exit 2
  export FAKE_PORT CONTROL_PORT READY_FILE="$RUN_DIR/fake.ready"
  rm -f "$READY_FILE"
  launch fake node_modules/.bin/tsx .local-data/accept/fake-world.mts
  wait_until 120 test -s "$RUN_DIR/fake.ready" || fail "假中台 120 秒內沒就緒，看 $RUN_DIR/fake.log" 6
  echo "假中台就緒"
  launch server npm run dev
  wait_until 240 curl -sf "http://127.0.0.1:$SERVER_PORT/api/v1/health/ready" || fail "Server 240 秒內沒就緒（含內嵌資料庫建立與 migration），看 $RUN_DIR/server.log" 6
  echo "Server 就緒：http://127.0.0.1:$SERVER_PORT"
  launch worker npm run worker:dev
  # 第一輪資料集發佈代表 Worker 讀完來源（含料件檔）並完成編譯；之前 manifest 只有共用資料集或是空的
  wait_until 180 grep -q 'dataset_compile_round_published' "$RUN_DIR/worker.log" || fail "Worker 180 秒內沒有發佈第一輪資料集，看 $RUN_DIR/worker.log" 6
  echo "Worker 已發佈第一輪資料集。就緒。日誌在 $RUN_DIR/"
}

cmd_status() {
  local n p
  for n in fake server worker; do
    if pid_alive "$n"; then echo "${n}：存活 pid=$(cat "$RUN_DIR/$n.pid")"; else echo "${n}：未執行"; fi
  done
  for p in "$DB_PORT" "$SERVER_PORT" "$FAKE_PORT" "$CONTROL_PORT"; do
    port_owner "$p" || echo "  埠 ${p}：沒有人在聽"
  done
  curl -s "http://127.0.0.1:$SERVER_PORT/api/v1/health/ready" || echo "Server 就緒檢查：連不上"
  echo
}

cmd_upsert() {
  [ $# -ge 2 ] || fail "用法：upsert <表名> '<表頭 JSON>' ['<表身 JSON>']" 2
  local body
  if [ $# -ge 3 ]; then body="{\"table\":\"$1\",\"record\":$2,\"lines\":$3}"; else body="{\"table\":\"$1\",\"record\":$2}"; fi
  curl -sf -X POST "http://127.0.0.1:$CONTROL_PORT/ctl/upsert" -d "$body"
  echo
}

cmd_down() {
  local n pid i p leftover
  # 先停 Worker 與 Server（避免 Worker 在資料庫關閉後報錯），最後停假中台
  for n in worker server fake; do
    pid_alive "$n" || continue
    pid="$(cat "$RUN_DIR/$n.pid")"
    kill -TERM "$pid" 2>/dev/null
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -0 "$pid" 2>/dev/null && echo "警告：${n}（pid=${pid}）20 秒內沒結束" >&2
  done
  # npm 的子行程有時不隨父殼結束：只處理 cwd 在本專案目錄底下的埠占用者
  for p in "$DB_PORT" "$SERVER_PORT" "$FAKE_PORT" "$CONTROL_PORT"; do
    for pid in $(lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null | sort -u); do
      case "$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')" in
        "$ABY_DIR"*) echo "殘留：埠 $p 的 pid=$pid 屬於本專案目錄，送 SIGTERM"; kill -TERM "$pid" 2>/dev/null ;;
        *) echo "不處理：埠 $p 的 pid=$pid 不在本專案目錄底下" >&2 ;;
      esac
    done
  done
  sleep 3
  leftover=0
  for p in "$DB_PORT" "$SERVER_PORT" "$FAKE_PORT" "$CONTROL_PORT"; do
    if port_owner "$p"; then leftover=1; fi
  done
  [ "$leftover" = 0 ] && echo "全部埠已釋放" || fail "仍有埠被占用（見上），請確認後處理" 7
}

cmd_clean() {
  cmd_down || exit $?
  rm -rf "$ABY_DIR/.dev-db" "$ABY_DIR/.local-data" "$ABY_DIR/.env"
  echo "已移除 .env、.dev-db、.local-data"
}

case "${1:-}" in
  prepare) cmd_prepare ;;
  up) cmd_up ;;
  status) cmd_status ;;
  upsert) shift; cmd_upsert "$@" ;;
  down) cmd_down ;;
  clean) cmd_clean ;;
  *) fail "用法：harness.sh <prepare|up|status|upsert|down|clean>" 2 ;;
esac
