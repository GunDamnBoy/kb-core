#!/usr/bin/env python3
"""哪一組標頭讓 urllib 過得去。**只讀不寫，約一分鐘。**

## 為什麼

2026-08-22：curl 對 TWSE 四個端點全部 200，而 urllib 同一秒、同一個 IP、
同一個 User-Agent 卻回 428／308。**所以那不是限流，是客戶端標頭的差異。**

我把診斷方向搞錯了整整三輪：看到 428 就假設是速率，於是去量速率、加冷卻、調間隔——
**都在解一個不存在的問題。** 對照組（curl）一開始就該做。

這一支把變因一次一個地加回去，找出**最小的那組必要標頭**。
"""
import gzip, io, time, urllib.request, urllib.error, zlib

URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20240301&selectType=MS&response=json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

VARIANTS = [
    ("A 什麼都不加（urllib 預設）", {}),
    ("B 只加 UA", {"User-Agent": UA}),
    ("C UA ＋ Referer", {"User-Agent": UA, "Referer": "https://www.twse.com.tw/"}),
    ("D C ＋ Accept:*/*", {"User-Agent": UA, "Referer": "https://www.twse.com.tw/",
                           "Accept": "*/*"}),
    ("E D ＋ Accept-Encoding:gzip", {"User-Agent": UA, "Referer": "https://www.twse.com.tw/",
                                     "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}),
    ("F 完整瀏覽器樣", {"User-Agent": UA, "Referer": "https://www.twse.com.tw/",
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Encoding": "gzip, deflate",
                        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                        "Connection": "keep-alive"}),
    ("G 只加 Accept-Encoding", {"Accept-Encoding": "gzip, deflate"}),
]


def body(resp):
    raw = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        raw = gzip.decompress(raw)
    elif "deflate" in enc:
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def once(hdrs, url=URL):
    req = urllib.request.Request(url)
    for k, v in hdrs.items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            b = body(r)
            ok = b'"stat"' in b[:200]
            return f"{r.status}{'' if ok else ' 但不是 JSON'}", len(b)
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", 0
    except Exception as e:
        return e.__class__.__name__, 0


print(f"{'標頭組合':<26}{'結果':<18}{'位元組':>8}")
print("-" * 54)
winner = None
for name, h in VARIANTS:
    st, n = once(h)
    print(f"{name:<26}{st:<18}{n:>8}")
    if winner is None and st.startswith("200") and "不是 JSON" not in st:
        winner = (name, h)
    time.sleep(2)

if not winner:
    print("\n**沒有一組過得去。** 那就不是標頭問題，貼回來再想。")
    raise SystemExit(1)

print(f"\n最小可用組合：**{winner[0]}**")
print("\n用它連打 15 次（間隔 0.4 秒），確認到底有沒有限流：")
ok = bad = 0
t0 = time.time()
for i in range(15):
    st, n = once(winner[1])
    if st.startswith("200"): ok += 1
    else: bad += 1; print(f"  第 {i+1} 次：{st}")
    time.sleep(0.4)
print(f"  成功 {ok}／15，失敗 {bad}，每筆 {(time.time()-t0)/15:.2f}s")
if bad == 0:
    n_req = 3100 * 2
    print(f"  → 沒有限流。逐日抓兩支端點約 {n_req} 次請求，"
          f"預估 {n_req*((time.time()-t0)/15)/60:.0f} 分鐘")
print("\n把整段貼回來。")
