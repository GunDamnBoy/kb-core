#!/usr/bin/env python3
"""管線 B 的 judge 段：把 raw 序列變成一份 draft。

真實系統裡這一段是模型在做判斷（挑題、寫判讀）。tracer bullet 用一個
機械的替身，因為這一片要驗的是**介面**不是判斷力——draft 的形狀、
verify 吃不吃得下、交棒通不通。

用法：make_draft.py <raw.json> <draft.json>
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.result import Exit  # noqa: E402

IDENT = "FRED:DGS10"


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return Exit.BAD_INPUT

    src, dst = Path(argv[1]), Path(argv[2])
    try:
        raw = json.loads(src.read_text())
        pts = raw["series"][IDENT]["points"]
    except FileNotFoundError:
        print(f"找不到 raw：{src}", file=sys.stderr)
        return Exit.BAD_INPUT
    except (json.JSONDecodeError, KeyError) as e:
        print(f"raw 結構不符：{e}", file=sys.stderr)
        return Exit.BAD_INPUT

    if not pts:
        print(f"{IDENT} 沒有任何點", file=sys.stderr)
        return Exit.BAD_INPUT

    last_d, last_v = pts[-1]
    ref = pts[-64] if len(pts) >= 64 else pts[0]
    chg_bp = round((last_v - ref[1]) * 100)

    # 序列末日與今天的落差。舊規格：落後 ≥2 天警示、≥5 天硬失敗。
    lag = (dt.date.today() - dt.date.fromisoformat(last_d)).days

    items = [
        {"k": "美債 10 年期", "v": f"{last_v:.2f}%", "asof": last_d},
        {"k": "近三個月變動", "v": f"{chg_bp:+d} bp", "from": ref[0]},
        {"k": "序列落後天數", "v": f"{lag} 天"},
    ]

    draft = {
        "date": dt.date.today().isoformat(),
        "upstream_date": raw["date"],
        "note": f"tracer bullet：由 {src.name} 產出，{IDENT} 共 {len(pts)} 點",
        "items": items,
        "provenance": {
            "derived_from": f"chart-of-the-day/raw/{src.name}",
            "raw_fetched_at": raw.get("fetched_at"),
        },
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(draft, ensure_ascii=False, indent=1))
    print(f"寫入 {dst}")
    for i in items:
        print(f"  {i['k']:<12} {i['v']}")
    return Exit.OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
