#!/usr/bin/env python3
"""限時執行器：這台機器沒有 timeout／gtimeout，而 npm run test:* 偶爾會卡死，背景執行時不能靠口頭預估等它自己結束。

用法（務必用 python3 -I 啟動，避免載入工作目錄裡的同名模組）：
  python3 -I run-with-timeout.py <總秒數上限> <無輸出秒數上限> <log 檔> -- <指令與參數...>

行為：
- 指令在自己的行程群組執行，輸出寫進 log 檔；
- 總時間超過上限，或 log 連續這麼久沒有新輸出，就對整個行程群組送 SIGTERM，5 秒後仍在就 SIGKILL（只會殺自己啟動的這一群，不用名稱樣式找行程）；
- 結束時在 log 最後一行寫 `EXIT=<結束碼> REASON=<finished|total_timeout|idle_timeout>`，因為 npm 與 vitest 串起來之後結束碼不可靠，判定一律看 log 內的測試摘要（例如 `Test Files … passed`）與這一行。
結束碼：自己的結束碼 0 表示指令正常結束（不代表測試通過）；3 表示被逾時終止。
"""
import os
import signal
import subprocess
import sys
import time


def main() -> int:
    if len(sys.argv) < 6 or sys.argv[4] != "--":
        print(__doc__)
        return 2
    total_limit: int = int(sys.argv[1])
    idle_limit: int = int(sys.argv[2])
    log_path: str = sys.argv[3]
    command: list[str] = sys.argv[5:]
    started: float = time.time()
    last_growth: float = started
    last_size: int = -1
    reason: str = "finished"
    with open(log_path, "wb") as log:
        process: subprocess.Popen[bytes] = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            time.sleep(2)
            size: int = os.path.getsize(log_path)
            if size != last_size:
                last_size = size
                last_growth = time.time()
            if time.time() - started > total_limit:
                reason = "total_timeout"
            elif time.time() - last_growth > idle_limit:
                reason = "idle_timeout"
            if reason != "finished":
                os.killpg(process.pid, signal.SIGTERM)
                time.sleep(5)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                break
        code: int = process.wait()
    with open(log_path, "ab") as log:
        log.write(f"\nEXIT={code} REASON={reason}\n".encode("utf-8"))
    return 0 if reason == "finished" else 3


if __name__ == "__main__":
    sys.exit(main())
