#!/usr/bin/env python3
"""量 TWSE 的限流，順便找有沒有「一次一個月」的端點。**只讀不寫，約兩分鐘。**

## 為什麼要有它

2026-08-22：`TWTB4U` 回 **HTTP 428**。那是限流訊號，不是資料問題。
而逐日抓 2014 起的三支端點 ＝ 約 9,300 次請求 ——
**在不知道可持續速率之前排這種工作，等於把一小時的估計拿去賭。**

兩件事要量出來：
1. **可持續速率**：間隔多久不會被擋、被擋之後多久恢復。
2. **有沒有批次端點**：`FMTQIK` 一次回一整月（已驗證，152 個月只花了幾秒）。
   若融資融券與當沖也有月批次，工作量會從幾小時掉到幾分鐘。
   **候選端點一律標明是猜的，回不出資料就是回不出，不進程式。**
"""
import json, time, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def get(url, timeout=25):
    r = urllib.request.Request(url)
    r.add_header("User-Agent", UA)
    r.add_header("Referer", "https://www.twse.com.tw/")
    r.add_header("Accept", "application/json,text/plain,*/*")
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read()


def try_url(url):
    try:
        b = get(url)
        j = json.loads(b)
        tabs = j.get("tables") or [j]
        rows = sum(len(t.get("data") or []) for t in tabs)
        return j.get("stat"), rows, None
    except urllib.error.HTTPError as e:
        return None, 0, f"HTTP {e.code}"
    except Exception as e:
        return None, 0, e.__class__.__name__


print("=" * 76)
print("一、批次端點候選（能一次回一個月的話，工作量差兩個數量級）")
print("=" * 76)
CAND = [
  ("已驗證：加權指數月表 FMTQIK",
   "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20240301&response=json"),
  ("猜：融資融券 帶月初日期",
   "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20240301&selectType=MS&response=json"),
  ("猜：三大法人 type=month",
   "https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate=20240301&type=month&response=json"),
  ("猜：三大法人 type=day",
   "https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate=20240301&type=day&response=json"),
  ("猜：當沖 月統計 TWTB4U",
   "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date=20240301&response=json"),
  ("猜：當沖 月統計 TWTBAU",
   "https://www.twse.com.tw/rwd/zh/dayTrading/TWTBAU?date=20240301&response=json"),
]
for name, url in CAND:
    stat, rows, err = try_url(url)
    print(f"  {name:<28} stat={str(stat):<6} 列數={rows:<5} {err or ''}")
    time.sleep(3)

print("\n" + "=" * 76)
print("二、可持續速率：不同間隔各連打 12 次，看哪一個間隔開始出現 428")
print("=" * 76)
U = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d}&selectType=MS&response=json"
DAYS = [f"2024{m:02d}{d:02d}" for m in (3, 4) for d in (4, 5, 6, 7, 8, 11)]
for gap in (0.25, 1.0, 2.0, 3.0):
    ok = bad = 0
    t0 = time.time()
    for d in DAYS:
        stat, rows, err = try_url(U.format(d=d))
        if err: bad += 1
        elif stat == "OK": ok += 1
        time.sleep(gap)
    print(f"  間隔 {gap:>4.2f}s：成功 {ok:>2}／失敗 {bad:>2}　"
          f"實測每筆 {(time.time()-t0)/len(DAYS):.2f}s"
          + ("　**開始被擋**" if bad else ""))
    if bad == 0:
        print(f"  → 間隔 {gap}s 沒被擋。以 9,300 次請求估，"
              f"總時長約 {9300*(gap+0.15)/3600:.1f} 小時")
        break
    time.sleep(20)      # 被擋過就先冷卻再測下一個間隔

print("\n把整段貼回來。這決定台股要逐日抓（幾小時）還是批次抓（幾分鐘）。")
