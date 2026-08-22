#!/usr/bin/env python3
"""第 2 步的替代路徑探測。**只讀不寫，三十秒。**

netcheck 顯示 FRED 逾時、CFTC Socrata 回 403。兩個都有替代路徑，
但**替代路徑要驗過才算數**——猜一個網址寫進程式，比沒有更糟。
"""
import socket, time, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

T = [
    ("FRED 純文字序列",   "https://fred.stlouisfed.org/data/DGS10.txt", None),
    ("FRED CSV＋起始日",  "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10&cosd=2015-01-01", None),
    ("ALFRED CSV",       "https://alfred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", None),
    ("CFTC 年度檔（財金期貨）", "https://www.cftc.gov/files/dea/history/fut_fin_txt_2024.zip", None),
    ("CFTC Socrata CSV",  "https://publicreporting.cftc.gov/api/views/98ig-3k9y/rows.csv?accessType=DOWNLOAD", None),
    ("CFTC 週報頁",       "https://www.cftc.gov/dea/futures/financial_lf.htm", None),
    ("Stooq 美債10年殖利率", "https://stooq.com/q/d/l/?s=10usy.b&i=d", None),
    ("Stooq SOXX",       "https://stooq.com/q/d/l/?s=soxx.us&i=d", None),
    ("CBOE VIX3M",       "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv", None),
    ("ICI 週資金流 xls",  "https://www.ici.org/combined_flows_data_2026.xls", None),
    ("AAII 問卷頁",       "https://www.aaii.com/sentimentsurvey/sent_results", None),
]


def probe(url, ref, timeout=30):
    r = urllib.request.Request(url)
    r.add_header("User-Agent", UA); r.add_header("Accept", "*/*")
    if ref: r.add_header("Referer", ref)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            b = f.read(2048)
            return f"OK {f.status}", len(b), time.time() - t0, b[:70]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", 0, time.time() - t0, b""
    except (socket.timeout, TimeoutError):
        return "逾時", 0, time.time() - t0, b""
    except Exception as e:
        return e.__class__.__name__, 0, time.time() - t0, b""


print(f"{'來源':<24}{'結果':<14}{'位元組':>7}{'秒':>6}  前幾個字")
print("-" * 96)
for name, url, ref in T:
    st, n, sec, head = probe(url, ref)
    prev = head.decode("utf-8", "replace").replace("\n", " ")[:45] if n else ""
    print(f"{name:<24}{st:<14}{n:>7}{sec:>6.1f}  {prev}")
print("\n整張表貼回來。這決定第 2 步（觸發器）要走哪條路，或要不要改到 GitHub Actions 上跑。")
