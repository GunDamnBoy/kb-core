#!/usr/bin/env python3
"""驗一天的五圖，不發布。

用法：chart_verify.py <資料 repo> [日期 YYYY-MM-DD]

    chart_verify.py ~/chart-of-the-day            # 驗 data/<今天>.json
    chart_verify.py ~/chart-of-the-day 2026-08-17 # 驗某一天（回測用）

## 為什麼要有這一支

`publish.py` 也會跑同一組檢查，但它跑完就發布。**「先看一眼再決定發不發」
需要一個不會產生副作用的入口** —— 尤其在重建期間，要拿舊封存回測新檢查。

payload 的組法**只有一個家**：`systems/chart.py` 的 `build()`。
publish 用它、這支也用它 —— 兩份組法遲早會漂，而漂的那天兩邊的判定會不一致，
卻沒有任何東西說得出是哪一邊變了。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
import systems  # noqa: F401,E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402
from systems.chart import build  # noqa: E402


# 每一條檢查會伸手去拿的 anchors 頂層鍵。缺一個就在這裡大聲失敗——
# **門檻取不到是設定壞了，不是資料壞了**，安靜跳過會讓整組檢查變成永遠 PASS。
REQUIRED = ["structure", "tracks", "lengths", "series", "diversity",
            "footer", "freshness", "size", "kinds", "data_paths",
            "rendering", "known_exceptions", "schedule", "prefetch", "quality"]


def main(argv) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return Exit.BAD_INPUT
    repo = Path(argv[1]).expanduser()
    if len(argv) == 3:
        date = argv[2]
    else:
        import datetime as dt
        date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d")

    src = repo / "data" / f"{date}.json"
    if not src.exists():
        print(f"找不到 {src} —— 那一天還沒有產出", file=sys.stderr)
        return Exit.EMPTY_ROUND
    doc = json.loads(src.read_text())
    payload = build(doc, repo)
    miss = [k for k in REQUIRED if k not in payload["anchors"]]
    if miss:
        print(f"chart/anchors.json 缺 {miss} —— 門檻沒有家，這一輪沒有資格判", file=sys.stderr)
        return Exit.BAD_INPUT
    # **檔案大小要用實際落地的那個數字**，不是序列化後重算的長度。
    #
    # 2026-09-04 訂正：這裡原本寫「兩者會因為縮排與編碼而差幾個百分點」，
    # 而當時 `build()` 量的是 compact，實測差 **1.65 倍**（243.5 vs 401.6 KB）。
    # `build()` 已改用 `day_json()`，所以對 2026-08-21 之後的封存兩者現在**相同**，
    # 這一行是冗餘的。留著是因為它對**舊方言那 12 份**仍然不冗餘：
    # 2026-08-05 至 08-17 的日檔存成 `separators=(",",":")`，比 `day_json` 還緊，
    # 拿 `day_json` 重算會高估它們的真實大小（實測 08-06：檔案 247.2 KB、重算 273.2 KB）。
    # **已發布的檔問「它多大」，答案只能是檔案本身。**
    payload["size_kb"] = src.stat().st_size / 1024
    print(f"{date}｜{len(doc.get('charts') or [])} 張圖｜{payload['size_kb']:.0f} KB｜{src}\n")
    return report(run_all(payload, suite="chart"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
