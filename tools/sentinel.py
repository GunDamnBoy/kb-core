#!/usr/bin/env python3
"""哨兵——跑在 GitHub Actions 上，回答「這套系統還活著嗎」。

用法：sentinel.py <資料 repo> <系統 id>

前四片證明了順利時會成功。這一支回答另一個問題：**沒成功的時候，誰會知道。**

三條刻意的設計：

1. **heartbeat 每次都寫，不管判定綠不綠。** heartbeat 的語意是「我跑過了」，
   不是「一切正常」。把它綁在成功路徑上，就再也分不出「哨兵說沒事」與
   「哨兵根本沒跑」——那正是這支程式要消滅的東西。

2. **judgement 寫成檔案，開 issue 的動作留在 workflow。** 這是一道 seam：
   判斷邏輯在 Python 裡可以離線測試，`gh` 的管線在 YAML 裡。反過來寫的話，
   「什麼情況該叫」就只能靠真的跑一次 Actions 才驗得到。

3. **prev 來自上一次的 heartbeat。** 「東西有沒有變少」這種問題，單張快照
   永遠答不出來——要有前一張才比得出來。
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
import systems  # noqa: F401,E402  匯入即登記
from kbcore.repo import check_destination  # noqa: E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit, Level  # noqa: E402
from kbcore.system import get as get_system  # noqa: E402

HEARTBEAT = "sentinel/heartbeat.json"
REPORT = "sentinel/report.md"


def load(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return Exit.BAD_INPUT
    repo, system_id = Path(argv[1]), argv[2]

    err = check_destination(repo, system_id)
    if err:
        print(f"DESTINATION  {err}", file=sys.stderr)
        return Exit.BAD_INPUT

    now = dt.datetime.now(dt.timezone.utc)
    hb_path = repo / HEARTBEAT
    prev = load(hb_path)

    index = load(repo / "data" / "index.json")
    if index is None:
        print("讀不到 data/index.json —— 這不是「還沒開始」，是東西不見了",
              file=sys.stderr)
        index = {}

    # **節奏由系統自己宣告**（`System.cadence_hours`），哨兵只做換算。
    # 認不出的 id 在上面的 `check_destination` 就擋掉了，所以這裡拿得到。
    sysdef = get_system(system_id)
    payload = {
        "now": now.isoformat(timespec="seconds"),
        "index": index,
        "prev": prev,
        "cadence_hours": sysdef.cadence_hours if sysdef else None,
        "ledger": load(repo / "ledger" / "ledger.json"),
    }

    results = run_all(payload, suite="sentinel")
    code = report(results)

    bad = [(c, o) for c, o in results if o.level in (Level.FAIL, Level.WARN)]
    summary = "；".join(f"{c.id}: {o.detail}" for c, o in bad) or "全部正常"

    # heartbeat 先寫，而且不管綠不綠都寫
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    hb_path.write_text(json.dumps({
        "at": now.isoformat(timespec="seconds"),
        "exit": code,
        "day_count": len((index or {}).get("days") or []),
        "latest_date": ((index or {}).get("days") or [{}])[0].get("date"),
        "summary": summary,
    }, ensure_ascii=False, indent=1))

    lines = [f"# 哨兵回報 · {now.isoformat(timespec='seconds')}", ""]
    for c, o in results:
        mark = {Level.PASS: "✅", Level.WARN: "⚠️", Level.FAIL: "❌",
                Level.SKIPPED: "⏭️", Level.ENV: "🌐"}[o.level]
        lines.append(f"- {mark} `{c.id}` {o.detail}".rstrip())
    lines += ["", "## 這輪檢查看不到的形態", ""]
    seen = []
    for c, _ in results:
        for b in c.blind_to:
            if b not in seen:
                seen.append(b)
                lines.append(f"- {b}")
    (repo / REPORT).parent.mkdir(parents=True, exist_ok=True)
    (repo / REPORT).write_text("\n".join(lines) + "\n")

    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
