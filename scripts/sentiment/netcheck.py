#!/usr/bin/env python3
"""先量、再跑。**這支三十秒跑完，只讀不寫。**

在花六十分鐘抓資料之前，先確認每一台主機通不通。
「抓到一半才發現某個來源不通」跟「一開始就知道」的差別，是一小時。

## 2026-08-22 訂正：只看狀態碼會給假陽性

第一版只檢查 HTTP 狀態碼與位元組數，於是 **Stooq 回 `200` ＋ 796 個位元組的
HTML 錯誤頁，被記成「OK」**。那頁裡一列資料都沒有。

**守衛量的是「有沒有回東西」，比它宣稱檢查的「回的是不是資料」低一階** ——
這跟這套系統一路撞到的是同一種毛病，而且這次是我自己寫的守衛。

修法：每個目標帶一個 `shape`，說明資料長什麼樣（CSV 標題、JSON 起始字元），
內容對不上就記 **格式不符**，不是 OK。
"""
import socket, ssl, sys, time
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# (名稱, 網址, referer, 內容長怎樣才算真的拿到資料)
TARGETS = [
    ("TWSE 加權指數月表", "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20240102&response=json", None, '"stat"'),
    ("TWSE 融資融券",     "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20240102&selectType=MS&response=json", "https://www.twse.com.tw/", '"stat"'),
    ("TWSE 當沖統計",     "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?response=json&date=20240102", "https://www.twse.com.tw/", '"stat"'),
    ("TAIFEX P/C 區間",   "https://www.taifex.com.tw/cht/3/pcRatioExcel?queryStartDate=2024/01/02&queryEndDate=2024/01/05", None, "日期"),
    ("TAIFEX 三大法人期貨", "https://www.taifex.com.tw/cht/3/futContractsDate", None, "未平倉"),
    ("FRED CSV",          "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", None, "DGS10"),
    ("Stooq 日線",        "https://stooq.com/q/d/l/?s=%5Espx&i=d", None, "Date,Open"),
    ("CBOE VIX CSV",      "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", None, "DATE,OPEN"),
    ("CBOE 每日統計",     "https://www.cboe.com/us/options/market_statistics/daily/", "https://www.cboe.com/", "PUT/CALL"),
    ("CFTC 年度檔",       "https://www.cftc.gov/files/dea/history/fut_fin_txt_2024.zip", None, "PK"),
    ("GitHub raw",        "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv", None, "DATE"),
]


def probe(url, referer, shape, timeout=25):
    """**回 200 不算通過，內容對得上 `shape` 才算。**"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA); req.add_header("Accept", "*/*")
    if referer: req.add_header("Referer", referer)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read(8192)
            head = b[:4096].decode("utf-8", "replace")
            if shape and shape not in head and not head.startswith(shape):
                return "格式不符", len(b), time.time() - t0
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
    for name, url, ref, shape in TARGETS:
        st, n, sec = probe(url, ref, shape)
        print(f"{name:<22}{st:<16}{n:>8}{sec:>7.1f}")
        if not st.startswith("OK"): bad.append(name)
    print()
    if bad:
        print("**通不了的：** " + "、".join(bad))
        print("把整張表貼回來——不要自己改參數重試。哪一項不通會改變下一步做什麼，")
        print("而不是只是換個寫法再試一次。")
        print("**「格式不符」代表主機有回應但回的不是資料**（通常是錯誤頁或反爬頁），")
        print("那跟連不上要分開處理。")
    else:
        print("全部可達。可以開始跑 tw_probe.py --fetch")


if __name__ == "__main__":
    main()
