# 排程與電源設定

這個目錄是**版控的那一份**，實際生效的是 `~/Library/LaunchAgents/` 裡的副本。
兩邊會漂移，而且 launchd 不會告訴你——所以有 `watch.external_binaries`
在讀實裝的 plist，還有下面那條對帳指令。

## 排程工作

<!-- 標題刻意不寫數字。2026-08-21 一天之內這個數字錯了三次（七→八→九，
     而實際是十），因為它是**表格數量的第二份副本**，而人只會記得改表格。
     數量只有一個家：底下那張表。 -->

| Label | 什麼時候 | 做什麼 |
|---|---|---|
| `com.kenny.podfetch` | 每天 01:00 | 抓昨夜新集、Gemini 轉錄，寫 `~/podcast-transcripts/<date>/` |
| `com.kenny.kbpublish` | 每 60 秒 | 發布**投顧**：`~/outbox/` → `advisory-rewrite` |
| `com.kenny.kbpublish.podcast` | 每 60 秒 | 發布**podcast**：`~/outbox/podcast/` → `podcast-knowledge-digest` |
| `com.kenny.kbwatch` | 每 4 小時 | 看門狗：Actions 上的哨兵還活著嗎、本機程式有沒有漂移 |
| `com.kenny.kbwatch.podcast` | 02／06／10／14／18／22 時 | podcast 的看門狗（`kbwatch-podcast.sh`）：哨兵＋`healthcheck.py` |
| `com.kenny.kbwatch.chart` | 00／04／08／12／16／20 時 | chart 的看門狗：只跑 `watch_sentinel.py`（chart 沒有 healthcheck） |
| `com.kenny.kbdocx.podcast` | 每天 04:00 | 把**已發布的**當日 JSON 排版成 Word（`kbdocx-podcast.sh`）→ `~/Documents/podcast-reports` |
| `com.kenny.kbprefetch.chart` | 每天 11:00 | 每日五圖的序列預抓（`kbprefetch-chart.sh`）→ `data/series` 快取 |
| `com.kenny.kbpublish.chart` | 每 60 秒 | 發布**每日五圖**：`~/outbox/chart/` → `chart-of-the-day` |
| `com.kenny.kbcorepush` | 每 300 秒 | 推 **kb-core 自己**（`push_kbcore.py`），帶靜置與自檢閘門 |

**一個 plist 只發一套系統。** `publish.py` 的參數是 `(outbox, repo, 系統 id)`
三件一組，沒有「多套」這個形態——一次只驗一組檢查、一個目的地，
才不會有「我到底在發哪一套」這個問題。

### 為什麼 kb-core 要另外一支，而不是讓 publish 順手推

三支 `kbpublish` 推的是**機器產生、發布後不可改寫**的 `data/`；
`kbcorepush` 推的是**人與模型正在改的原始碼**，而且是另外三支
**執行中所依賴**的那份原始碼。兩者的閘門問的是不同的問題：

| | `kbpublish.*` | `kbcorepush` |
|---|---|---|
| 閘門 | 內容檢查（那一套系統的 suite） | `py_compile` ＋ 檢查自檢 |
| 觸發 | outbox 有草稿 | 工作區靜置 5 分鐘且有未推的東西 |
| 落後 origin | `pull --rebase` 續推 | **停下來報告，不自動 rebase** |

最後一列是刻意的：在三套排程跑的同時改寫 kb-core 的工作區，
等於讓它們的 `import checks` 有機會讀到一個寫到一半的檔。
單一寫入者的 repo 落後 origin 本來就代表有人在別處動過，
**那是需要人看的狀況，不是該自動化掉的狀況。**

閘門三比前兩道重要：**推壞掉的 `checks/` 上去，三套系統的閘門會同時失效，
而它們的回執還是會說成功。** 一個推不上去的 repo 只是不方便，
一個推上去的壞閘門是靜默失效。

回執在 `~/kb-core/.push-receipt.json`（已 gitignore —— 不擋掉的話它每輪重寫
會讓工作區永遠是髒的，於是每 5 分鐘 commit 一次自己的回執）。

### 為什麼 podcast 那一支是釘整點，advisory 那一支是每 4 小時

兩者問的問題對「什麼時候問」的敏感度不同。`watch_sentinel` 問「GitHub 上的哨兵
活著沒」——任何時刻問答案都一樣，`StartInterval` 的相位無所謂。
`healthcheck.py` 會去讀當天的日檔、逐字稿與線上站台，**答案跟時點有關**，
而 `StartInterval` 的相位取決於載入時刻，遲早會漂到 03:00 的日報中間。

釘在整點就沒有這個問題：**02:00** 在 podfetch（01:00）之後、官方稿（02:20）與
日報（03:00）之前；**06:00** 是日報發完之後的第一次，人起床時已經有兩份報告了。

### 為什麼預抓釘在 11:00

它跟 `chart/anchors.json` 的 `schedule.prefetch`／`schedule.run`（11:00／11:30）是**一組的**，
不是各寫各的。預抓 46 條實測約 9 分鐘，11:00 起跑留半小時緩衝。
**動了 anchors 的時刻就要回頭動這支 plist** —— 反過來也一樣。
漂掉的樣子不是失敗，是那一輪安靜地用了前一日快取。

### 為什麼 Word 是一支 launchd 而不是日報那一輪的最後一步

`podcast_docx.py` 全程不需要 LLM —— 它只排版，一個字都不改。
留在日報那一輪等於為了一段純機械的工作，多要一個資料夾掛載
（`~/Documents/podcast-reports`），而 2026-08-21 那一輪就是因為那個掛載請求
被中斷、**發布 exit 0、Word 卻沒有**。

搬出來之後還多了一層好處：逐字稿與 Word 檔留在所有 repo 外面是結構性的界線，
而「不必連進任何 LLM 工作階段」讓那條界線又厚了一層。

**順序仍然是先發布、後轉檔**：這支先問回執、且只認 `exit 0`，
所以不會出現「Word 有這集、網站沒有」。

### 為什麼 `healthcheck.py` 只掛在 podcast 這一支

它是節目知識庫專屬的。兩支都掛的話它一天跑 12 次而不是 6 次，
而且 advisory 那邊拿它一點用都沒有。

### 為什麼是一支 shell 而不是把 healthcheck 塞進 `watch_sentinel.py`

看門狗的依賴要**比它守的東西少**。`watch_sentinel` 目前只需要 `git fetch`；
`healthcheck` 需要網路、`~/.podfetch`、逐字稿目錄。合併等於讓看門狗長出三個
新的失敗點，而那三個之中任何一個壞掉，都會讓看門狗自己變紅、把真正的訊號埋掉。

## 安裝／重載

```bash
cp ~/kb-core/launchd/com.kenny.X.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.kenny.X.plist
launchctl bootout  gui/$(id -u)/com.kenny.X 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kenny.X.plist
launchctl list | grep kenny
```

`launchctl list` 那一欄是**上次的結束狀態，不是健康狀態**。
`kbpublish` 在沒有草稿的日子永遠是 `13`（EMPTY_ROUND），那是設計上的正常。
`kbprefetch.chart` 一天只跑一次，**平常問它會得到「沒跑過」而不是「失敗」** —— 這兩者長得很像。
`kbdocx.podcast` 在沒有回執、或回執非 0 的那一天回 `13`（EMPTY_ROUND），那也是設計上的正常。
**別養成看 `launchctl list` 判死活的習慣**，那是哨兵的工作。

## 跟版控對帳

實裝的 plist 與這裡不一致時沒有任何自動訊號，所以要手動問：

```bash
for f in ~/kb-core/launchd/com.kenny.*.plist; do
  n=$(basename "$f")
  diff -q "$f" ~/Library/LaunchAgents/"$n" >/dev/null 2>&1 \
    && echo "OK   $n" || echo "漂移 $n"
done
```

## 金鑰：跟 `pmset` 同一類，換機器不會跟著走

FRED 與 Tiingo 的 key **不在任何 repo 裡**（刻意的），所以 `git clone` 拿不到它們，
`git status` 也不會提。2026-08-20 換到 Mac mini 之後首次手動跑預抓才發現三樣都不在：

```bash
ls -l ~/.config/fred/api_key ~/.config/tiingo/api_key    # 兩個都要存在且 600
```

重建 —— 跑這支，key 用貼的：

```bash
bash ~/kb-core/launchd/setup-keys.sh          # 或 setup-keys.sh fred / tiingo
```

它會提示、收下貼上的內容（`read -rs`，畫面不回顯）、剃掉前後空白與換行、
寫檔並 `chmod 600`，然後立刻打一次網路驗證。三件事各有理由：

- **不要把 key 寫在指令列裡**，那會進 shell history，而那個檔案不會過期。
- **貼上很容易多帶一個換行或尾隨空白**，而多一個字元的 key 不會回「格式錯」，
  只會回 400 —— 看起來像「這把 key 沒有權限」，於是人去查權限而不是查空白。
- **寫檔成功與金鑰可用是兩件獨立的事**，所以寫完立刻驗，不讓「檔案存在」冒充「能用」。

長度不符（FRED 32 碼、Tiingo 40 碼）與覆蓋既有檔案都會再問一次，預設是不做。

**它壞掉的樣子是安靜跑二十分鐘然後全部失敗。** 沒有 key 就退到 `fredgraph.csv`，
而那條路在這台機器上不通（`chart/SOURCES.md`，Errno 60），於是每一條各自逾時 30 秒，
一條快取都不寫。`kbprefetch-chart.sh` 現在會在起飛前問一次金鑰，讀不到就 `exit 14` 中止 ——
**這個問題要在兩秒內問完，不是二十分鐘後。**

台股（證交所、櫃買）免金鑰，所以「只有美股與總經整片消失、台股正常」是這個病的典型樣子。

## 電源：`pmset` 不在任何設定檔裡

`pmset` 寫的是韌體層的排程與設定。**repo 裡看不到、`git status` 不會提、
換機器不會跟著走**，而它壞掉的樣子是「一切正常，只是晚了六小時」——
launchd 遇到機器睡著不會叫醒它，會把那一輪留到下次醒來才補跑。

重建時要跑這兩行（都要 sudo）：

```bash
sudo pmset sleep 0                                    # 全天候主機，不睡
sudo pmset repeat wakeorpoweron MTWRFSU 00:55:00      # 停電／重開機後的保險
```

確認：

```bash
pmset -g sched && pmset -g custom | grep -E '^ *(sleep|displaysleep|disksleep|womp)'
```

要看到 `sleep 0` 與 `Repeating power events: wakepoweron at 0:55AM every day`。

**`sleep 0` 是主要防線，00:55 的喚醒是保險。** 反過來設會失效：
2026-08-19 實測 `sleep 1`（閒置一分鐘就睡），00:55 醒來後 00:56 就睡回去，
01:00 的排程照樣撲空——**喚醒窗口比等待時間還短。**

## 哨兵的時刻與 36 小時門檻是一組的

哨兵不在這台機器上跑（它是 GitHub Actions，`<repo>/.github/workflows/sentinel.yml`），
但它的時刻要跟這裡的排程一起看：

| repo | cron (UTC) | 台北 |
|---|---|---|
| advisory-rewrite | `0 7` | 15:00 |
| chart-of-the-day | `20 7` | 15:20 |
| podcast-knowledge-digest | `30 7` | 15:30 |

`sentinel.data_fresh` 的年齡從那一天的**台北零時**起算、上限 36 小時，
所以「昨天那一期」在**次日中午 12:00 台北**跨線。哨兵排在那之後才問得出
「今天這一期出來了沒」；排在之前就只問得出「昨天那一期還在不在」。

2026-08-21 之前三個都排在 11:00–11:30，**距離那條線只有 30–60 分鐘**，
於是同時有兩種錯：管線整天沒產出會判綠（35 小時還沒過線），
管線只是跑晚了會判紅。而 GitHub 排程延遲動輒數十分鐘 ——
**一個判決取決於 cron 準不準時的檢查，會隨機紅、隨機綠。**

## 已知的坑

- **`kbwatch` 一次只看得了一套系統。** 2026-08-20 之前它指的是 `kb-tracer`，
  於是四條檢查裡有兩條（`sentinel_alive`、`sentinel_verdict`）讀的是靶子的
  heartbeat，另外兩條照常正確——**不會全紅，只會缺一半**，所以撐了兩天沒被發現。
  podcast 那一支已經另外建了 `com.kenny.kbwatch.podcast`。
  chart 那一支在 2026-08-21 補上（`com.kenny.kbwatch.chart`）。
- **可重用 workflow 的 caller 一定要自己給 `permissions`。** chart 的 `sentinel.yml`
  漏了那一段，於是從 08-20 建立到 08-21 一次都沒成功跑過（唯一那次 `startup_failure`），
  `sentinel/heartbeat.json` 在遠端是 404。**而沒有心跳跟「哨兵判綠」在遠端看起來
  都是「沒有紅字」** —— 真正發現它的是「為什麼這個檔不存在」，不是任何一條檢查。
- **`launchd` 的環境是空的**：`PATH=/usr/bin:/bin:/usr/sbin:/sbin`、`cwd=/`。
  所以每個 plist 都明寫 `PATH`、`HOME`、`WorkingDirectory`，程式路徑一律絕對路徑。
- `com.kenny.podfetch` 的 `PATH` 多帶了 `/opt/homebrew/bin`，
  是為了哪天真的裝 ffmpeg 不用改 plist。**ffmpeg 是選配**——
  找不到就走內建切檔，2026-08-20 十集實測全部走 pure-python，沒有一集出問題。
