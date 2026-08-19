#!/bin/bash
# 把 launchd com.kenny.podfetch 的執行時刻改回 01:00（必須早於 03:00 的日報）。
# 2026-08-03 建立：巡檢發現實際設在 07:00，比日報晚四小時，會讓日報每天讀不到當天逐字稿。
# 用法：bash ~/.podfetch/fix-schedule.sh

set -u
PLIST="$HOME/Library/LaunchAgents/com.kenny.podfetch.plist"
LABEL="com.kenny.podfetch"

if [ ! -f "$PLIST" ]; then
  echo "找不到 $PLIST — 請確認 launchd agent 的檔名。"
  exit 1
fi

echo "== 修改前 =="
/usr/libexec/PlistBuddy -c "Print :StartCalendarInterval" "$PLIST" 2>/dev/null || echo "(無 StartCalendarInterval)"

cp "$PLIST" "$PLIST.bak.$(date +%Y%m%d%H%M%S)"

/usr/bin/python3 - "$PLIST" <<'PY'
import plistlib, sys
p = sys.argv[1]
with open(p, 'rb') as f:
    d = plistlib.load(f)
# StartCalendarInterval 可能是 dict 或 list of dict，兩種都處理
d['StartCalendarInterval'] = {'Hour': 1, 'Minute': 0}
with open(p, 'wb') as f:
    plistlib.dump(d, f)
print("已寫入 StartCalendarInterval = 01:00")
PY

echo "== 修改後 =="
/usr/libexec/PlistBuddy -c "Print :StartCalendarInterval" "$PLIST"

echo "== 重新載入 =="
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"
launchctl list | grep "$LABEL" || echo "警告：launchctl list 找不到 $LABEL"

echo
echo "完成。明天早上請確認 ~/.podfetch/logs/\$(date +%F).log 開頭時間戳是 [01:00:0x]。"
echo "備份留在 $PLIST.bak.*，要還原直接覆蓋回去再 launchctl unload/load。"
