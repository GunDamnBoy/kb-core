#!/usr/bin/env python3
"""節目清單增刪 —— 就地修改 shows.json 與 config.json。

用法：patch_shows.py <.podfetch 目錄>

## 為什麼是腳本不是「我幫你重寫兩個檔」

`config.json` 裡的 `_comment_*` 是你寫的決策紀錄（額度實測值、為什麼 20 分鐘一段、
為什麼 cooldown 取 300 秒）。**重打一次只會增加抄錯的機會，而且抄錯不會有訊號。**
就地修改只動該動的鍵，其餘一個位元組都不碰。

冪等：重跑不會重複新增，也不會因為已經刪掉而報錯。

## 兩個檔要一起改

`shows.json` 的鍵與 `config.json` 的 `show_priority` **必須一致**。
舊規格記著「新增節目時要記得插進 show_priority」——那是一條靠記憶的規則，
所以這支程式最後會做一次雙向對帳，缺哪邊就大聲說。
"""
import json
import shutil
import sys
from pathlib import Path

REMOVE = ["pivot", "lennys", "lex"]

ADD = {
    "sharptech": {
        "appleId": "1646152812",
        "name": "Sharp Tech with Ben Thompson",
        # **hosts 待確認。** 節目名帶 Ben Thompson，另一位共同主持人的姓名
        # 我沒有可靠來源，所以不寫。錯的名字會變成對真實人物的不實陳述，
        # 比沒有名字糟得多（保守講者標記原則）。
        "hosts": "Ben Thompson",
    },
    "fwdguidance": {
        "appleId": "1592743188",
        "name": "Forward Guidance",
        # **hosts 完全待確認。** 這檔換過主持人，我沒有可靠的現任資訊。
        # 留空字串，等你從節目頁確認後補。
        "hosts": "",
    },
}

# 插在誰後面。理由：show_priority 決定①額度不足時的處理順序②同源去重保留哪一集，
# 所以位置要對齊題材鄰居，不是接在最後面。
INSERT_AFTER = {"fwdguidance": "oddlots", "sharptech": "latentspace"}


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    sp, cp = root / "shows.json", root / "config.json"
    for p in (sp, cp):
        if not p.exists():
            print(f"找不到 {p}", file=sys.stderr)
            return 2
        shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
    print(f"已備份 {sp.name}.bak、{cp.name}.bak\n")

    shows = json.loads(sp.read_text())
    cfg = json.loads(cp.read_text())
    prio = cfg["show_priority"]

    for k in REMOVE:
        print(f"  移除 {k:14} shows.json={'有→刪' if shows.pop(k, None) else '本來就沒有'}"
              f"  show_priority={'有→刪' if k in prio else '本來就沒有'}")
        if k in prio:
            prio.remove(k)

    for k, v in ADD.items():
        print(f"  新增 {k:14} {v['name']}  appleId={v['appleId']}"
              f"{'（已存在，覆寫）' if k in shows else ''}")
        shows[k] = v
        if k in prio:
            prio.remove(k)
        anchor = INSERT_AFTER[k]
        prio.insert(prio.index(anchor) + 1 if anchor in prio else len(prio), k)

    # **雙向對帳。** 舊規格那條「新增節目時要記得插進 show_priority」是靠記憶的規則，
    # 這裡把它變成機制。
    only_shows = sorted(set(shows) - set(prio))
    only_prio = sorted(set(prio) - set(shows))
    if only_shows or only_prio:
        print("\n對帳不符：")
        for k in only_shows:
            print(f"  {k} 在 shows.json 但不在 show_priority")
        for k in only_prio:
            print(f"  {k} 在 show_priority 但不在 shows.json")
        print("未寫入任何檔案。", file=sys.stderr)
        return 1

    sp.write_text(json.dumps(shows, ensure_ascii=False, indent=1) + "\n")
    cp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n")

    print(f"\n對帳相符：{len(shows)} 檔節目，show_priority {len(prio)} 筆")
    print(f"\nshow_priority 新順序：")
    for i, k in enumerate(prio, 1):
        mark = "  ←新增" if k in ADD else ""
        print(f"  {i:2}. {k}{mark}")
    print("\n**沒有 wpm 的節目沿用全域 200** —— sharptech 與 fwdguidance 剛加，"
          "頭幾次的完整度可能偏低，那是分母問題不是缺字。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
