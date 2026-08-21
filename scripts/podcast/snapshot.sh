#!/bin/bash
# snapshot.sh — 把「不在 git 裡」的系統檔案存成一份快照。
#
# 為什麼需要：repo 內的 AGENT_BRIEF.md／MAINTENANCE.md／index.html 有 git，但
# 這一週改動最頻繁的檔案全都在 repo 外——podfetch.py 至少改了 8 次、排程
# SKILL.md 至少 9 次而且**被整份覆寫過一次**（2026-08-04），當時完全無法還原。
#
# 用法：
#   bash ~/.podfetch/snapshot.sh                 # 存一份快照
#   bash ~/.podfetch/snapshot.sh 開工前           # 加註說明
#   bash ~/.podfetch/snapshot.sh --list          # 列出所有快照
#   bash ~/.podfetch/snapshot.sh --diff A B      # 比對兩份快照
#
# 還原：直接 cp 回去即可，例如
#   cp ~/.podfetch/snapshots/<時間戳>/podfetch.py ~/.podfetch/podfetch.py
#
# **gemini.key 一律排除**，快照裡不會有金鑰。

set -u

# 掛載點偵測（2026-08-16 新增）——與 healthcheck.py 的 resolve() **順序相同**：
# 先找 Cowork 沙箱的 /sessions/*/mnt，再退回家目錄。Mac 上沒有 /sessions，行為不變。
# **但「找不到」時的語意不同**：Python 版兩處都找不到會回 None（呼叫端隨即跳過），
# 這裡則無條件回 $HOME/.podfetch（不管它存不存在）——由下方的 copied 守衛兜住。
#
# 沒有這段的後果不是「跑不動」，而是**安靜地產生一份空快照**：沙箱裡 $HOME 不是
# /Users/kenny，於是每個檔案都印「（缺）」，然後照樣建目錄、寫 MANIFEST、回報
# 「快照完成」——那筆會出現在 --list 裡，看起來就是一個正常的還原點。
# 而 repo 外的檔案沒有 git，快照是唯一還原點。
resolve_base() {
  for m in /sessions/*/mnt; do
    [ -d "$m/.podfetch" ] && { printf '%s' "$m/.podfetch"; return; }
  done
  printf '%s' "$HOME/.podfetch"
}
BASE="$(resolve_base)"
SNAP="$BASE/snapshots"
# 排程 SKILL.md 的位置**歷史上換過兩次**：目錄從 ~/Documents/Claude 移到 ~/Claude，
# 任務名從 podcast-digest-daily 改成 podcast-daily-300（2026-08-21 在 MAIN.md 訂正過
# taskId，但沒有人回頭改這裡）。硬寫路徑的後果不是報錯——`copy()` 只印一行
# 「（缺）SKILL.md」，而**那正是沙箱缺它時的正常訊息**，所以在 Mac 上跑也看不出差別。
# 2026-08-22 查證時發現這條路徑已經指向不存在的位置，而 SKILL.md 正是「一定要在 Mac
# 上跑一次」的唯一理由。改成掃描候選位置，找不到時明確出聲。
find_skill() {
  for d in "${HOME}/Claude/Scheduled" "${HOME}/Documents/Claude/Scheduled"; do
    [ -d "$d" ] || continue
    for n in podcast-daily-300 podcast-digest-daily; do
      [ -f "$d/$n/SKILL.md" ] && { printf '%s' "$d/$n/SKILL.md"; return; }
    done
    # 名字再改一次也要抓得到：任何含 podcast 的排程目錄。
    for p in "$d"/*podcast*/SKILL.md; do
      [ -f "$p" ] && { printf '%s' "$p"; return; }
    done
  done
  printf ''
}
SKILL="$(find_skill)"

list_snaps() {
  [ -d "$SNAP" ] || { echo "還沒有任何快照。"; return; }
  for d in "$SNAP"/*/; do
    [ -d "$d" ] || continue
    n=$(basename "$d")
    note=$(sed -n '2p' "$d/MANIFEST.txt" 2>/dev/null | sed 's/^說明：//')
    printf "%-22s %s\n" "$n" "$note"
  done
}

case "${1:-}" in
  --list) list_snaps; exit 0 ;;
  --diff)
    A="$SNAP/${2:-}"; B="$SNAP/${3:-}"
    [ -d "$A" ] && [ -d "$B" ] || { echo "用法：$0 --diff <快照A> <快照B>"; list_snaps; exit 1; }
    echo "== $2 → $3 =="
    for f in podfetch.py healthcheck.py json2docx.py config.json shows.json SKILL.md fix-schedule.sh; do
      if [ -f "$A/$f" ] || [ -f "$B/$f" ]; then
        if ! diff -q "$A/$f" "$B/$f" >/dev/null 2>&1; then
          echo; echo "--- $f ---"
          diff -u "$A/$f" "$B/$f" 2>/dev/null | head -80
        fi
      fi
    done
    exit 0 ;;
esac

NOTE="${1:-未註明}"
# **TZ 要驗，不能只設**（2026-08-17 複驗時發現）：tzdata 缺席或時區名打錯時，
# `date` 會**靜默退回 UTC 且離開碼 0**——快照照建、MANIFEST 照寫、--list 照列，
# 症狀與修法前一模一樣而且無跡可循。所以這裡實際核對偏移量是不是 +0800。
if [ "$(TZ=Asia/Taipei date +%z)" != "+0800" ]; then
  echo "★時區警告：TZ=Asia/Taipei 沒有生效（date +%z 回 $(TZ=Asia/Taipei date +%z)），" >&2
  echo "  快照時間戳將是 UTC，--list 的排序會與其他快照錯開 8 小時。" >&2
fi
TS=$(TZ=Asia/Taipei date +%Y-%m-%d-%H%M%S)   # 到秒。分鐘級時同一分鐘兩次快照會靜默互相覆蓋
# **時區要寫死（2026-08-17 修）**：原本用執行環境的本地時間，在 Mac 上是台北、
# 在 Cowork 沙箱裡卻是 UTC，於是沙箱取的快照名會早 8 小時。`--list` 是照目錄名
# 排序的，8/17 早上取的快照因此排到了 8/16 晚上那幾筆前面——**快照鏈的順序會錯亂，
# 而它是還原時唯一的線索**。昨天補掛載點偵測時只修了路徑、沒修時間。
DEST="$SNAP/$TS"
if [ -d "$DEST" ]; then DEST="$DEST-2"; fi   # 同秒重跑也不覆蓋
mkdir -p "$DEST"

copied=0
copy() {  # copy <來源> <存成的檔名>
  if [ -f "$1" ]; then cp "$1" "$DEST/$2"; copied=$((copied+1)); else echo "  （缺）$2"; fi
}

copy "$BASE/podfetch.py"      podfetch.py
copy "$BASE/healthcheck.py"   healthcheck.py
copy "$BASE/json2docx.py"     json2docx.py
copy "$BASE/snapshot.sh"      snapshot.sh
copy "$BASE/fix-schedule.sh"  fix-schedule.sh
copy "$BASE/config.json"      config.json
copy "$BASE/shows.json"       shows.json
copy "$SKILL"                 SKILL.md
# **SKILL.md 缺席在沙箱裡是正常的，在 Mac 上是故障**，而 `copy()` 對兩者印一樣的字。
# 這裡把它們分開：沙箱的 BASE 一定在 /sessions/ 底下。
case "$BASE" in
  /sessions/*) : ;;   # 沙箱：看不到排程目錄是預期的，不出聲
  *)
    if [ -z "$SKILL" ] || [ ! -f "$SKILL" ]; then
      echo "★找不到排程 SKILL.md —— 這份快照不能當還原點用。" >&2
      echo "  找過：${HOME}/Claude/Scheduled 與 ${HOME}/Documents/Claude/Scheduled" >&2
      echo "  排程的實際路徑可用 Claude 的 list_scheduled_tasks 取得，取到後回頭改 find_skill()。" >&2
    fi ;;
esac
# state.json 是執行狀態不是設定，快照它只會製造雜訊；gemini.key 是金鑰，一律不存。

# 一個都沒抄到＝BASE 解析錯了。**空快照比沒有快照更危險**——它看起來像還原點。
# 所以出聲、自刪，不要留下假的還原點。（SKILL.md 單獨缺是正常的：沙箱看不到
# ~/Documents，那是 macOS TCC 保護區。）
if [ "$copied" -eq 0 ]; then
  rmdir "$DEST" 2>/dev/null
  echo "★快照失敗：在 $BASE 底下一個檔案都找不到。已刪除空目錄，未留下假還原點。" >&2
  echo "  BASE 解析結果：$BASE" >&2
  exit 1
fi

{
  echo "快照時間：$TS"
  echo "說明：$NOTE"
  echo "（gemini.key 與 state.json 刻意排除）"
  echo
  printf "%-18s %8s  %s\n" 檔案 位元組 SHA256前16
  for f in "$DEST"/*; do
    b=$(basename "$f")
    [ "$b" = "MANIFEST.txt" ] && continue
    sz=$(wc -c < "$f" | tr -d ' ')
    sha=$(shasum -a 256 "$f" | cut -c1-16)
    printf "%-18s %8s  %s\n" "$b" "$sz" "$sha"
  done
} > "$DEST/MANIFEST.txt"

# **`$VAR` 後面緊接全形字元一律加大括號**（2026-08-17 ③）：macOS 的 bash 是 3.2.57，
# 它的識別字掃描會把 `（`（U+FF08，EF BC 88）那幾個高位元組吃進變數名，於是「`$DEST` 緊接
# 全形括號」被當成一個叫 `DEST\xef\xbc\x88…` 的未設定變數，`set -u` 當場中止。
# **沙箱是 bash 5.1，解析完全正常——所以這個 bug 只在 Mac 上出現，**
# **而 Mac 正是唯一能取得完整快照（含 SKILL.md）的地方。在沙箱跑一百次也測不到。**
#
# 守衛（本註解刻意不寫出那個壞掉的字面組合，好讓這道掃描保持零命中）：
#   perl -ne 'print "$ARGV:$.: $_" if /\$[A-Za-z_]\w*(?=[^\x00-\x7F])/' ~/.podfetch/*.sh
# **用 perl 不用 `grep -P`**：macOS 內建的是 BSD grep、不支援 `-P`，而 Mac 正是唯一
# 會出這個 bug 的機器——守衛在它該防的環境上跑不起來，就等於沒有守衛。
echo "快照完成：${DEST}（來源 BASE＝${BASE}）"
cat "$DEST/MANIFEST.txt"
