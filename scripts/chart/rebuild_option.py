# -*- coding: utf-8 -*-
"""
rebuild_option.py — 重建既有某一天的**衍生產物**（`option` 欄位、可選 PNG／SVG），
其餘一律不動。事實（`series`）與紀錄（`about.run`、`qa_flags`）永遠不碰。

**為什麼不能用 `render_day.py` 回補舊期**：它會順便重新計算 `qa_flags` 並覆寫。
旗標門檻改過（6σ→5σ、加連續日合併）之後，重跑會產生與當初不同的旗標，
而 `about.run` 裡已經寫好的處置說明是對著**當初那組旗標**寫的——兩者一旦對不上，
歷史紀錄就從「誠實回報」變成「說明與資料不符」。**修渲染不該動到紀錄。**

本工具只碰 `charts[].option`：
    不動 series（事實）、不動 about.run 與 qa_flags（紀錄）、不動 files（產物路徑）、
    不動 headline / standfirst / window 等任何其他欄位。
執行前後會逐欄位比對並印出差異，確認真的只有 option 變了才寫檔。

用法：
    python3 ~/kb-core/scripts/chart/rebuild_option.py 2026-08-05 2026-08-06
    python3 ~/kb-core/scripts/chart/rebuild_option.py --all
    python3 ~/kb-core/scripts/chart/rebuild_option.py --dry-run 2026-08-05      # 只看差異不寫檔
    python3 ~/kb-core/scripts/chart/rebuild_option.py --png --all               # 同時重繪 PNG／SVG

何時該用：`chartkit` 修了會影響既有圖表呈現的缺陷時。
  · 2026-08-06 首次使用：ECharts category 軸的位置對應 bug——序列長度不同就整條位移，
    網頁錯而 PNG 對（見 AGENT_BRIEF 第 8 節第 7 版）。
  · 2026-08-08 加入 `--png`：頁尾原本沒有換行機制，超出圖框直接被裁且不留痕跡，
    既有 2026-08-05 有一筆 `note` 視覺寬 224。**PNG 是 House View 月報直接取用的檔案**，
    所以那是實際流出去的缺陷，不是只影響網站。

`--png` 會覆寫 `charts/<date>/*.png` 與 `.svg`。**那兩個目錄同樣是衍生產物**——
由未更動的 JSON 重繪，圖上的數字不會變，變的只有排版。
"""
from __future__ import annotations
import glob, json, os, sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
# 同目錄的兄弟模組。舊制是 os.path.join(REPO, "tools")——
# 那綁在「程式住在資料 repo 底下」這個佈局上，搬家就斷。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chartkit as ck                                    # noqa: E402
from render_day import to_chart                          # noqa: E402


def rebuild(day: str, dry: bool = False, png: bool = False) -> bool:
    path = os.path.join(REPO, "data", f"{day}.json")
    if not os.path.exists(path):
        print(f"✗ {day}：找不到 {path}")
        return False
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    changed = []
    for c in doc.get("charts", []):
        old = c.get("option")
        new = ck.echarts_option(to_chart(c))
        if old != new:
            changed.append(c.get("slug", "?"))
        c["option"] = new

    # 守門：把 option 全部挖掉之後，其餘內容必須與原檔逐字相同。
    # 這是「只動 option」這句話的實際驗證，不是靠相信自己寫對了。
    def strip(d):
        d = json.loads(json.dumps(d))
        for ch in d.get("charts", []):
            ch.pop("option", None)
        return json.dumps(d, ensure_ascii=False, sort_keys=True)

    if strip(json.loads(before)) != strip(doc):
        print(f"✗ {day}：option 以外的欄位也變了，已中止，未寫檔")
        return False

    if dry:
        msg = f"會更新 {len(changed)} 張圖的 option：{changed}" if changed else "option 已是最新"
        if png:
            msg += f"；會重繪 {len(doc.get('charts', []))} 張 PNG／SVG"
        print(f"·  {day}：（dry-run）{msg}")
        return True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"✓  {day}：已更新 {len(changed)} 張圖的 option：{changed}")
    else:
        print(f"·  {day}：option 已是最新，無需變更")

    # PNG／SVG 由未更動的 JSON 重繪。**檔名沿用 files 欄位裡既有的路徑**，
    # 不重新編號——`files` 是紀錄的一部分，重繪不該讓它改變。
    if png:
        outdir = os.path.join(REPO, "charts", day)
        n = 0
        for i, c in enumerate(doc.get("charts", []), 1):
            rel = (c.get("files") or {}).get("png")
            base = os.path.splitext(os.path.basename(rel))[0] if rel else f"{i:02d}-{c['slug']}"
            ck.render_static(to_chart(c), outdir, base)
            n += 1
        print(f"✓  {day}：已重繪 {n} 張 PNG／SVG（數字未變，只有排版）")
    return True


if __name__ == "__main__":
    # **不認得的旗標要大聲失敗。** 舊寫法是逐個 `in sys.argv` 比對，
    # 於是打錯的旗標（`--dry` vs `--dry-run`）不會有任何反應 ——
    # 它只是沒被認出來，然後**照正常模式跑完並寫檔**。
    # 2026-08-20 就是這樣改寫掉一份已發布的封存，而輸出看起來完全正常
    #（「✓ 已更新 2 張圖」讀起來很像 dry-run 的差異報告）。
    KNOWN = {"--dry-run", "--png", "--all"}
    unknown = [a for a in sys.argv[1:] if a.startswith("--") and a not in KNOWN]
    if unknown:
        sys.exit(f"不認得的旗標 {unknown} —— 認得的是 {sorted(KNOWN)}。"
                 "**這裡刻意不猜**：這支工具的預設行為是寫檔，"
                 "而打錯的旗標若被忽略，結果是安靜地改寫已發布的封存。")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    png = "--png" in sys.argv
    if "--all" in sys.argv:
        args = sorted(os.path.basename(p)[:-5]
                      for p in glob.glob(os.path.join(REPO, "data", "2*.json")))
    if not args:
        print(__doc__)
        sys.exit(1)
    ok = all(rebuild(d, dry, png) for d in args)
    # dashpush 已於 2026-08-20 退休。**改動不會自己上線** ——
    # 這支只動工作區，要進站上得走 outbox 草稿與 publish 那條路。
    print("\n提醒：本工具不跑 git，改動只在工作區。"
          "要上站請走 ~/outbox/chart/ 的草稿與 publish；歷史封存原則上不回頭改寫。")
    sys.exit(0 if ok else 1)
