#!/usr/bin/env python3
"""先量、再跑。**這支三十秒跑完，只讀不寫。**

在花六十分鐘抓資料之前，先確認每一台主機通不通。
「抓到一半才發現某個來源不通」跟「一開始就知道」的差別，是一小時。
"""
import socket, ssl, sys, time
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TARGETS = [
    ("TWSE 加權指數月表", "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20240102&response=json", None),
    ("TWSE 融資融券",     "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20240102&selectType=MS&response=json", "https://www.twse.com.tw/"),
    ("TWSE 當沖統計",     "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?response=json&date=20240102", "https://www.twse.com.tw/"),
    ("TAIFEX P/C 區間",   "https://www.taifex.com.tw/cht/3/pcRatioExcel?queryStartDate=2024/01/02&queryEndDate=2024/01/05", None),
    ("TAIFEX 三大法人期貨", "https://www.taifex.com.tw/cht/3/futContractsDate", None),
    ("FRED CSV",          "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", None),
    ("Stooq 日線",        "https://stooq.com/q/d/l/?s=%5Espx&i=d", None),
    ("CBOE VIX CSV",      "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", None),
    ("CBOE 每日統計",     "https://www.cboe.com/us/options/market_statistics/daily/", "https://www.cboe.com/"),
    ("CFTC Socrata",      "https://publicreporting.cftc.gov/resource/98ig-3k9y.json?$limit=1", None),
    ("GitHub raw",        "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv", None),
]


def probe(url, referer, timeout=25):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    if referer: req.add_header("Referer", referer)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read(4096)
            return f"OK {r.status}", len(b), time.time() - t0
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", 0, time.time() - t0
    except (socket.timeout, TimeoutError):
        return "逾時", 0, time.time() - t0
    except ssl.SSLError as e:
        return f"TLS {e.__class__.__name__}", 0, time.time() - t0
    except Exception as e:
        return f"{e.__class__.__name__}", 0, time.time() - t0


def main():
    print(f"{'來源':<22}{'結果':<16}{'前 4KB':>8}{'秒':>7}")
    print("-" * 55)
    bad = []
    for name, url, ref in TARGETS:
        st, n, sec = probe(url, ref)
        print(f"{name:<22}{st:<16}{n:>8}{sec:>7.1f}")
        if not st.startswith("OK"): bad.append(name)
    print()
    if bad:
        print("**通不了的：** " + "、".join(bad))
        print("把整張表貼回來——不要自己改參數重試。哪一項不通會改變下一步做什麼，")
        print("而不是只是換個寫法再試一次。")
    else:
        print("全部可達。可以開始跑 tw_probe.py --fetch")


if __name__ == "__main__":
    main()
