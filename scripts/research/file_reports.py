#!/usr/bin/env python3
"""抽過的原文 → `filed/<YYYY-MM>/`。**這支會搬走你的原文。**

用法：file_reports.py <inbox> [--filed <目錄>] [--extracted <目錄>] [--move]

**預設只報不搬。** 要真的動手才加 `--move` —— 跟 `assemble.py` 的 `--publish`
同一條：危險的那一步要明講。這支搬的是**原始 PDF**，而原文在這一套裡是
唯一沒有第二份的東西（`extracted/` 是衍生的，重抽得回來；PDF 弄丟就沒了）。

## 為什麼要有這一步

`anchors.identity.archive` 從 2026-08-21 就寫著「處理後移進 `filed/<YYYY-MM>/`」，
但一直沒有人實作，於是 inbox 變成一個只長不消的堆。
2026-08-23 inbox 改接 Google Drive 的 `Report Inbox` 之後這件事升級了：
**那個堆從本機搬到了個人雲端**，而報告逐頁蓋著收件人的公司信箱與逐份追蹤雜湊
（見 `anchors.privacy.watermark_is_pii`）。整套系統為了那個浮水印，
連私有 repo 都不准放原文 —— 讓它在雲端永久累積跟那條界線是矛盾的。

**這支存在的理由就是讓雲端那一格排空。** 處理完的原文回到本機封存，
雲端只留還沒處理的那幾份。

## 為什麼不做成 `extract.py` 的一個旗標

因為**它們跑在不同的地方**。`extract.py` 在 Cowork 的排程階段跑；
那個階段的沙箱**不准刪檔**，而跨掛載的 `mv` 是「複製 ＋ 刪來源」——
2026-08-23 實測：複製成功、刪來源失敗、`mv` 回非零，
但**目的地已經有一份完整的檔，來源也還在**。

> 「已封存」與「已封存但原檔還在雲端」，在 log 上長得一模一樣。

所以這支要跑在 Mac 上（launchd，`com.kenny.kbfile.research`），
那裡沒有那層限制。**分成兩支不是潔癖，是因為執行環境的能力不同。**

## 只搬「已經抽過而且抽的就是這一份」的

判準是 **sha256 對得上**，不是檔名對得上：檔名會因為 Drive 的同名消歧義
變成 `xxx (1).pdf`，而那時內容是一樣的。用內容判，才不會把一份還沒抽過的
新檔當成抽過的搬走。

再加一條：`extracted/<slug>.json` 的 mtime 要比 PDF 新。
**PDF 動過但還沒重抽的，不搬** —— 那份的抽取結果已經過期，
搬走等於把「該重抽」這件事的唯一線索藏起來。

## 搬完要驗

`shutil.move` 回來不代表搬成功（見上面那段）。每一筆都驗三件事：
目的地在、目的地的 sha256 跟搬之前一樣、**來源不見了**。
第三件是重點 —— 前兩件在「複製成功但沒刪掉」的情況下都會過。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402   路徑只有一個家，見該檔的檔頭


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("inbox", nargs="?")
    ap.add_argument("--filed", default=None)
    ap.add_argument("--extracted", default=None)
    ap.add_argument("--move", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, unknown = ap.parse_known_args(argv)
    if a.help or not a.inbox:
        print(__doc__); return 2
    if unknown:
        # 跟 extract.py 同一個守衛，理由也一樣：argparse 的前綴展開會把
        # `--mo` 當成 `--move`。`allow_abbrev=False` 讓這個守衛真的擋得住。
        print(f"不認得的旗標 {unknown} —— **這裡刻意不猜**", file=sys.stderr)
        return 12

    inbox = os.path.expanduser(a.inbox)
    filed = os.path.expanduser(a.filed) if a.filed else _paths.under("filed")
    ext = os.path.expanduser(a.extracted) if a.extracted else _paths.extracted()
    if not os.path.isdir(inbox):
        print(f"找不到 {inbox} —— **跟「資料夾是空的」是兩件事**", file=sys.stderr)
        return 12
    if not os.path.isdir(ext):
        print(f"找不到 {ext} —— 還沒抽過的話這一步沒有意義", file=sys.stderr)
        return 12

    # sha256 → (slug, json 路徑, 報告日期)。**用內容當鍵，不是檔名。**
    by_sha = {}
    for f in sorted(glob.glob(os.path.join(ext, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  略過不合法的 JSON：{os.path.basename(f)}", file=sys.stderr)
            continue
        if d.get("sha256"):
            by_sha[d["sha256"]] = (d.get("slug"), f, d.get("date"))

    pdfs = sorted(os.path.join(inbox, f) for f in os.listdir(inbox)
                  if f.lower().endswith(".pdf"))
    if not pdfs:
        print("inbox 沒有 PDF —— 空輪次，不是失敗")
        return 0

    print(f"{len(pdfs)} 份在 inbox｜{len(by_sha)} 份抽取結果"
          + ("　**dry-run，不搬**" if not a.move else f" → {filed}"))

    moved = stale = unknown_n = 0
    fail = []
    for p in pdfs:
        name = os.path.basename(p)
        h = sha256(p)
        hit = by_sha.get(h)
        if not hit:
            print(f"  留著　{name[:58]:<58} 還沒抽過（或抽的是別的版本）")
            unknown_n += 1
            continue
        slug, jpath, date = hit
        if os.path.getmtime(jpath) < os.path.getmtime(p):
            # PDF 比抽取結果新 —— 抽取結果過期了。搬走它，
            # 「該重抽」這件事就再也沒有東西會提醒你。
            print(f"  留著　{name[:58]:<58} **抽取結果比 PDF 舊，先重抽**")
            stale += 1
            continue

        # 分月用的是**報告自己的日期**，不是檔案的 mtime ——
        # 一份 6 月的報告 8 月才進 inbox，它屬於 filed/2026-06。
        # 這跟 `assemble.py` 依報告日期分期是同一條規則。
        ym = (date or "0000-00")[:7]
        dstdir = os.path.join(filed, ym)
        dst = os.path.join(dstdir, name)
        if os.path.exists(dst):
            # 不覆蓋。同名不同內容的話，覆蓋掉的是那份唯一沒有第二份的東西。
            if sha256(dst) == h:
                print(f"  已在封存　{name[:54]:<54} {ym}／同一份，inbox 這份可以清掉")
            else:
                print(f"  **衝突**　{name[:54]:<54} {ym} 已有同名但內容不同的檔，沒有動")
                fail.append(name)
            continue

        print(f"  搬　　{name[:58]:<58} → {ym}/  （{slug}）")
        if not a.move:
            continue
        os.makedirs(dstdir, exist_ok=True)
        try:
            shutil.move(p, dst)
        except OSError as e:
            print(f"      **搬不動**：{type(e).__name__}: {e}")
            fail.append(name)
            continue

        # ── 搬完的三項驗證 ────────────────────────────────────────
        # 第三項是重點：跨掛載的 move 是「複製 ＋ 刪來源」，
        # 而在不准刪檔的環境裡前兩項照樣會過。
        if not os.path.exists(dst):
            print("      **目的地沒有東西**"); fail.append(name); continue
        if sha256(dst) != h:
            print("      **目的地的內容跟搬之前不一樣**"); fail.append(name); continue
        if os.path.exists(p):
            print(f"      **來源還在** —— 複製成功但沒刪掉，{inbox} 裡那份還在。\n"
                  "        這個環境不准刪檔（Cowork 的排程階段就是這樣）。\n"
                  "        這支要跑在 Mac 上（launchd），不是 Cowork 階段裡。")
            fail.append(name)
            continue

        # 抽取結果記下它搬去哪了。**`extract.py` 的孤兒判準靠這一欄**，
        # 不然封存過的那幾份下一輪會全部被判成孤兒。
        d = json.load(open(jpath, encoding="utf-8"))
        d["archived_to"] = os.path.join(ym, name)
        d["archived_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        moved += 1

    print(f"\n搬了 {moved} 份｜還沒抽過 {unknown_n} 份｜抽取結果過期 {stale} 份"
          + (f"｜**{len(fail)} 份出問題**" if fail else ""))
    if not a.move:
        print("  （沒有加 `--move`，一份都沒有真的搬）")
    for n in fail[:6]:
        print("   ", n)
    return 10 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
