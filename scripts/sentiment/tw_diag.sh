#!/bin/bash
# TWSE 到底回了什麼：看標頭，不猜。
U="https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20240301&selectType=MS&response=json"
echo "=== 1. 不跟導向，看原始回應標頭 ==="
curl -s -D - -o /dev/null --max-time 20 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36" \
  -H "Referer: https://www.twse.com.tw/" \
  "$U" | head -20

echo
echo "=== 2. 跟導向（-L），看最後拿到什麼 ==="
curl -sL --max-time 20 -w "\n[最終狀態 %{http_code}　最終網址 %{url_effective}　位元組 %{size_download}]\n" \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36" \
  -H "Referer: https://www.twse.com.tw/" \
  "$U" | head -c 400

echo
echo "=== 3. 對照組：FMTQIK（剛才成功的那支）==="
curl -s -o /dev/null -w "狀態 %{http_code}　位元組 %{size_download}\n" --max-time 20 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36" \
  "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20240301&response=json"

echo
echo "=== 4. 當沖 TWTB4U ==="
curl -s -o /dev/null -w "狀態 %{http_code}　位元組 %{size_download}\n" --max-time 20 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36" \
  -H "Referer: https://www.twse.com.tw/" \
  "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?response=json&date=20240301"
