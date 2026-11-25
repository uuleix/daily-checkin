"""统一签到入口：依次执行灵犀、WPS会员签到，聚合结果。

每个子任务独立子进程执行，互不干扰；任一失败则整体退出码非零，
由调度器决定是否推送微信。
"""

import json
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, "daily_checkin_log.txt")
STATUS_PATH = os.path.join(BASE, "daily_checkin_status.json")

# (任务名, 脚本文件)
TASKS = [
    ("灵犀", "lingxi_checkin.py"),
]


def write_log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def classify(output, returncode):
    if "NEED_RELOGIN" in output:
        return "NEED_RELOGIN"
    if "OK:" in output and returncode == 0:
        return "OK"
    if "FAIL" in output or "ERROR" in output or "WARN" in output:
        return "FAIL"
    return "FAIL" if returncode != 0 else "UNKNOWN"


def extract_detail(output):
    for line in reversed(output.splitlines()):
        s = line.strip()
        if not s:
            continue
        for prefix in ("OK:", "FAIL:", "ERROR:", "NEED_RELOGIN:", "WARN:"):
            if prefix in s:
                return s[s.index(prefix):].strip()
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    return lines[-1] if lines else "无输出"


def main():
    results = []
    for name, script in TASKS:
        path = os.path.join(BASE, script)
        if not os.path.exists(path):
            results.append({"task": name, "status": "FAIL", "detail": f"脚本不存在: {script}"})
            write_log(f"{name}: FAIL 脚本不存在")
            continue

        try:
            proc = subprocess.run(
                [sys.executable, path],
                cwd=BASE,
                text=True,
                capture_output=True,
                timeout=240,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            output = "ERROR: 执行超时"
            proc = None
        except Exception as exc:
            output = f"ERROR: {exc}"
            proc = None

        rc = proc.returncode if proc else 1
        status = classify(output, rc)
        detail = extract_detail(output)
        results.append({"task": name, "status": status, "detail": detail})
        write_log(f"{name}: {status} | {detail}")

    # 写状态文件，供外部查看
    summary = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "all_ok": all(r["status"] == "OK" for r in results),
    }
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    failed = [r for r in results if r["status"] != "OK"]
    if not failed:
        write_log("全部成功")
        return 0

    write_log(f"存在失败项: {[r['task'] for r in failed]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
