#!/bin/bash
# podcast 那一套的看門狗。**兩件事，一次跑完，退出碼取較差的那個。**
#
# 為什麼是一支 shell 而不是塞進 watch_sentinel.py：
#   兩者問的問題不同。watch_sentinel 問「GitHub 上的哨兵還活著嗎」——只 fetch、
#   不碰工作區、對 repo 的內容一無所知。healthcheck 問「整套東西健康嗎」——
#   跨 20 天日檔、推送鏈、線上站台。把後者塞進前者，等於讓看門狗長出它不該有的
#   依賴（網路、~/.podfetch、逐字稿目錄），而那些東西任何一個壞掉都會讓看門狗
#   自己變成紅的，然後真正的訊號被埋掉。
#
# 為什麼 healthcheck 只掛在 podcast 這一支：它是**節目知識庫專屬**的。
# 兩支 kbwatch 都掛的話，它一天會跑 12 次而不是 6 次，而且 advisory 那邊
# 拿它一點用都沒有。
#
# **這支不跑任何 git 指令。** watch_sentinel 內部自己只做 fetch；
# healthcheck 的 docstring 明寫「絕不呼叫 git」——背景推送會被 .git/index.lock 擋住。
set -o pipefail
PY=/Users/macmini/.venvs/kb/bin/python
echo "──────── $(date '+%Y-%m-%d %H:%M:%S') kbwatch.podcast"

"$PY" /Users/macmini/kb-core/tools/watch_sentinel.py \
      /Users/macmini/podcast-knowledge-digest podcast-knowledge-digest
a=$?

"$PY" /Users/macmini/kb-core/scripts/podcast/healthcheck.py
b=$?

# healthcheck 的 FAIL 不該把看門狗的退出碼蓋掉，反過來也一樣：
# 兩個都要看得見，所以取較大的那個，並且把兩個原值印出來。
echo "watch_sentinel=$a  healthcheck=$b"
[ "$a" -ge "$b" ] && exit "$a" || exit "$b"
