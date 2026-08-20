#!/usr/bin/env python3
"""驗當天那一輪 podfetch 的取數品質。

用法：podcast_verify.py <逐字稿根目錄> [日期 YYYY-MM-DD]

    podcast_verify.py ~/podcast-transcripts
    podcast_verify.py ~/podcast-transcripts 2026-08-20

## 為什麼是獨立一支，不是塞進 podfetch

podfetch 半夜 01:00 跑，出問題的時候人在睡覺。**判定與執行分開**，
才能在早上用同一組檢查重跑一次同一份 manifest，而不必重抓一次音檔。

同一個理由也讓 payload 的組裝集中在這裡：檢查本身不做 IO，
所以「manifest 在哪、shows 在哪、anchors 在哪」只有這一個家。

## 逐字稿在 repo 外面，這支程式不改變那件事

它只讀 manifest，不讀 `.md`、不寫任何東西。
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

TPE = dt.timezone(dt.timedelta(hours=8))


def main(argv) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return Exit.BAD_INPUT

    root = Path(argv[1]).expanduser()
    date = argv[2] if len(argv) == 3 else dt.datetime.now(TPE).strftime("%Y-%m-%d")
    mf = root / date / "manifest.json"

    if not mf.exists():
        # 「那一輪沒跑」與「跑了但沒收到東西」是兩件事，而這裡只看得出前者。
        print(f"EMPTY_ROUND  找不到 {mf} —— 那一輪沒有產出 manifest",
              file=sys.stderr)
        return Exit.EMPTY_ROUND

    try:
        manifest = json.loads(mf.read_text())
    except json.JSONDecodeError as e:
        print(f"BAD_INPUT  {mf} 不是合法的 JSON：{e}", file=sys.stderr)
        return Exit.BAD_INPUT

    payload = {
        "manifest": manifest,
        "shows": json.loads((ROOT / "scripts/podcast/shows.json").read_text()),
        "anchors": json.loads((ROOT / "podcast/anchors.json").read_text()),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    print(f"{date}｜{len(manifest.get('episodes') or [])} 集｜{mf}")
    return report(run_all(payload, suite="podcast"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
