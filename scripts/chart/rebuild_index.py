# -*- coding: utf-8 -*-
"""
rebuild_index.py — 重建 data/index.json。

原本每天由執行者自己寫一段掃描程式碼重建索引——同一段邏輯每天重寫一次，
既花 token 又可能各天寫得不一樣。索引的欄位是前端契約，該由一份程式碼定義。

    python3 ~/kb-core/scripts/chart/rebuild_index.py
"""
from __future__ import annotations
import glob, json, os

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()

days = []
for p in sorted(glob.glob(os.path.join(REPO, "data", "2*.json")), reverse=True):
    d = json.load(open(p, encoding="utf-8"))
    days.append({
        "date": d["date"], "weekday": d.get("weekday", ""),
        "headline": d.get("headline", ""), "charts": len(d.get("charts", [])),
        "themes": [c.get("theme", "") for c in d.get("charts", [])],
        "slots": [c.get("slot", "") for c in d.get("charts", [])],
    })

idx = {"title": "每日五圖 · Chart of the Day",
       "updated": days[0].get("date", "") if days else "",
       "days": days}
# updated 沿用最新一期的 data_asof（若有）
if days:
    latest = json.load(open(os.path.join(REPO, "data", f"{days[0]['date']}.json"), encoding="utf-8"))
    idx["updated"] = (latest.get("window") or {}).get("data_asof", days[0]["date"])

out = os.path.join(REPO, "data", "index.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(idx, f, ensure_ascii=False, indent=1)
print(f"✓ index.json：{len(days)} 期，最新 {days[0]['date'] if days else '—'}")
