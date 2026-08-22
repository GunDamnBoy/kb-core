#!/usr/bin/env python3
"""TAIFEX 的區間查詢能不能一次拿多天。**只讀不寫，約一分鐘。**

## 為什麼

`futContractsDateDown` 的表單有 `queryStartDate` 與 `queryEndDate` 兩個欄位，
而我一直**把兩個都填成同一天**——等於有區間查詢卻逐日打了 652 次，然後撞 429。

這跟 `FMTQIK` 是同一個教訓：**那支一次回一整月，152 個月幾秒就抓完**。
端點本來就支援批次，只是我沒用。

**先試三種區間長度，看它到底回多少天。** 回得了一年，652 次就變 13 次。
"""
import csv, io, time, urllib.parse, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
URL = "https://www.taifex.com.tw/cht/3/futContractsDateDown"


def post(a, b, timeout=60):
    body = urllib.parse.urlencode({
        "firstDate": a, "lastDate": b, "queryStartDate": a, "queryEndDate": b,
        "commodityId": "TXF"}).encode()
    req = urllib.request.Request(URL, data=body)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://www.taifex.com.tw/cht/3/futContractsDate")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def probe(a, b, label):
    try:
        raw = post(a, b)
    except urllib.error.HTTPError as e:
        print(f"  {label:<22} HTTP {e.code}"); return
    except Exception as e:
        print(f"  {label:<22} {e.__class__.__name__}"); return
    rows = list(csv.reader(io.StringIO(raw)))
    dates = set()
    for r in rows:
        for c in r[:2]:
            c = str(c).strip()
            if len(c) == 10 and c[4] in "/-" and c[:4].isdigit():
                dates.add(c)
    print(f"  {label:<22} 回 {len(rows):>5} 列、涵蓋 {len(dates):>4} 個不同日期"
          f"　{min(dates) if dates else ''}→{max(dates) if dates else ''}")
    if len(rows) > 2 and not dates:
        print(f"        （抓不到日期欄，前兩列：{rows[0][:4]} / {rows[1][:4] if len(rows)>1 else ''}）")


print("TAIFEX 三大法人期貨：區間查詢能回多少天\n")
for a, b, lab in [
    ("2024/03/01", "2024/03/01", "單日"),
    ("2024/03/01", "2024/03/08", "一週"),
    ("2024/03/01", "2024/03/29", "一個月"),
    ("2024/01/01", "2024/12/31", "一整年"),
]:
    probe(a, b, lab)
    time.sleep(8)      # TAIFEX 會擋，慢慢來
print("\n回得了一個月或一年的話，652 次請求就變成 13 次或 1 次。整段貼回來。")
