#!/usr/bin/env python3
"""部署之後，確認**線上那份就是剛上傳的那份**。

用法：verify_live.py <站台網址> <本地檔> [站台上的相對路徑，預設 data/index.json]

## 為什麼比雜湊，不比欄位

舊規格第十節記著：2026-08-03 那次 `days[0].date` 早就是當天日期，
**只看日期會被騙**，所以 podcast 後來補了 `updatedLabel`。
那是對的修法，但它的形狀是一張會過期的清單 —— schema 下次再長一個欄位，
這張清單又要記得補，而忘記補的時候不會有任何徵兆。

雜湊沒有這個問題：它問的是「線上那份跟我剛上傳的那份是不是同一個檔」，
**schema 怎麼變都成立**，也不需要知道哪些欄位重要。

## 為什麼在部署之後，不在哨兵裡

驗證要貼著它要驗的那個動作。哨兵 03:00 UTC ＝ 台北 11:00 跑，
而投顧大約 11:00–13:00 才發布 —— 它每天看到的是前一天的狀態，
當日部署失敗要隔天才叫得出來。

## 三種結果要分得出來

**拿不到**（網路、404、Pages 沒開）與**拿到但是舊的**（CDN 還沒換、或部署根本沒生效）
是兩件事，處置也不同。訊息要說得出是哪一種 —— 一個含糊的「驗證失敗」
會讓下一個人從頭查起。
"""
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# CDN 換頁要時間。舊規格量到的是 2–4 分鐘，所以預算給到 5 分鐘出頭。
DELAYS = [0, 15, 15, 30, 30, 60, 60, 60, 60]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def main(argv) -> int:
    if not 3 <= len(argv) <= 4:
        print(__doc__)
        return 2
    base = argv[1].rstrip("/")
    local = Path(argv[2])
    rel = argv[3] if len(argv) == 4 else "data/index.json"

    if not local.exists():
        print(f"本地找不到 {local} —— 這不是部署問題，是上傳的內容就不對", file=sys.stderr)
        return 2
    want = hashlib.sha256(local.read_bytes()).hexdigest()
    print(f"要比對的是 {local}（sha256 {want[:12]}…）")

    last = None
    waited = 0
    for i, d in enumerate(DELAYS):
        if d:
            time.sleep(d)
            waited += d
        url = f"{base}/{rel}?cb={int(time.time())}"
        try:
            body = _fetch(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = f"拿不到：{type(e).__name__} {e}"
            print(f"  第 {i+1} 次（+{waited}s）{last}")
            continue
        got = hashlib.sha256(body).hexdigest()
        if got == want:
            print(f"線上與剛上傳的完全一致（等了 {waited} 秒）")
            return 0
        last = f"拿到了但不是同一份（線上 sha256 {got[:12]}…）"
        print(f"  第 {i+1} 次（+{waited}s）{last}")

    print(f"\n等了 {waited} 秒仍未一致 —— {last}", file=sys.stderr)
    if last and last.startswith("拿不到"):
        print("**這一種是「連不上」**：Pages 沒開、網址錯、或部署根本沒產生站台。",
              file=sys.stderr)
    else:
        print("**這一種是「站台還在服務舊的那份」**：部署沒生效，或 CDN 超出預期地慢。\n"
              "網站此刻對讀者顯示的是舊內容，而回執與哨兵都會是綠的。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
