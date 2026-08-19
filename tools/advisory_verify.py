#!/usr/bin/env python3
"""投顧知識庫的檢查進入點——把 payload 組出來，交給 advisory suite。

用法：advisory_verify.py <資料 repo> <當日的 json>

檢查本身不做 IO（`checks/advisory.py` 只吃已經讀好的 dict），所有讀檔在這裡。

**前一版取「小於當日的最大日期」，不是「最新的非當日」。**
歷史重跑時後者會拿到未來的那一版，跨版去重整個反過來。
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

ANCHORS = "advisory/anchors.json"

# 每一個檢查會伸手去拿的 anchors 鍵。缺一個就在這裡大聲失敗——
# **門檻取不到是設定壞了，不是資料壞了**，安靜跳過會讓整組檢查變成永遠 PASS。
REQUIRED = ["groups", "site_total", "lengths", "fixed_structure",
            "base_card_groups", "dedup_exempt"]


def prev_doc(data_dir: Path, date: str):
    days = sorted(f.stem for f in data_dir.glob("*.json")
                  if f.stem != "index" and f.stem < date)
    return json.loads((data_dir / f"{days[-1]}.json").read_text()) if days else None


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return Exit.BAD_INPUT
    repo, doc_path = Path(argv[1]), Path(argv[2])

    anchors_path = repo / ANCHORS
    if not anchors_path.exists():
        anchors_path = ROOT / ANCHORS
    if not anchors_path.exists():
        print(f"找不到 {ANCHORS} —— 門檻沒有家，這一輪沒有資格判", file=sys.stderr)
        return Exit.BAD_INPUT

    anchors = json.loads(anchors_path.read_text())
    missing = [k for k in REQUIRED if k not in anchors]
    if missing:
        print(f"{ANCHORS} 缺少檢查會用到的鍵：{'、'.join(missing)}", file=sys.stderr)
        return Exit.BAD_INPUT

    try:
        doc = json.loads(doc_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"讀不開 {doc_path}：{e}", file=sys.stderr)
        return Exit.BAD_INPUT

    payload = {
        "doc": doc,
        "prev": prev_doc(repo / "data", doc.get("date", "")),
        "anchors": anchors,
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    print(f"對照前一版：{(payload['prev'] or {}).get('date', '無')}")
    return report(run_all(payload, suite="advisory"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
