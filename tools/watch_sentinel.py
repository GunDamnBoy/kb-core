#!/usr/bin/env python3
"""看門狗——跑在 Mac 上，看的是「哨兵還活著嗎」。

用法：watch_sentinel.py <資料 repo 的本機 clone> <系統 id>

**為什麼這支非得在 GitHub 外面跑**，寫在 `checks/watch.py` 的模組 docstring 裡。
一句話：GitHub 會在 60 天無活動時自動停用排程 workflow，於是看守者跟被看守的
東西綁在同一個開關上。Mac 不在那個開關的管轄範圍內。

**為什麼讀 origin/main 而不是工作區**：本機 clone 的工作區可能落後、可能因為
publish 正在動而髒掉。要問的問題是「哨兵在 GitHub 上有沒有跑」，那就該去看
GitHub 上的東西，不是看本機的影子。這裡只 fetch，不動工作區，跟 publish 井水
不犯河水。
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
from kbcore.repo import check_destination  # noqa: E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

HEARTBEAT = "sentinel/heartbeat.json"

# 只看真的會被執行的東西。README 改了沒 commit 不是事故。
CODE_DIRS = ("kbcore", "checks", "tools")


def code_drift():
    """本機這份 kb-core 有沒有跟 HEAD 漂移。回傳檔名清單；None 表示問不到。

    對象是 ROOT——也就是**這支程式自己所在的 repo**。程式問的是「我是不是版控裡
    的那個我」，不是「別的地方有沒有髒東西」。
    """
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--",
                        *CODE_DIRS], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [ln[3:] for ln in r.stdout.splitlines() if ln.strip()]


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return Exit.BAD_INPUT
    repo, system_id = Path(argv[1]), argv[2]

    err = check_destination(repo, system_id)
    if err:
        print(f"DESTINATION  {err}", file=sys.stderr)
        return Exit.BAD_INPUT

    fetched = subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin"],
                             capture_output=True, text=True)
    if fetched.returncode != 0:
        # 取不到遠端就**不要判**。判「哨兵死了」會是誤報，判「沒事」是謊話。
        print(f"ENVIRONMENT  fetch 失敗，本輪不判定："
              f"{(fetched.stderr or '').strip()[:200]}", file=sys.stderr)
        return Exit.ENVIRONMENT

    shown = subprocess.run(
        ["git", "-C", str(repo), "show", f"origin/main:{HEARTBEAT}"],
        capture_output=True, text=True)
    hb = None
    if shown.returncode == 0:
        try:
            hb = json.loads(shown.stdout)
        except json.JSONDecodeError:
            hb = None

    payload = {
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "heartbeat": hb,
        "drift": code_drift(),
    }
    return report(run_all(payload, suite="watch"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
