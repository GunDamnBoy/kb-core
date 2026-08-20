# 排程與電源設定

這個目錄是**版控的那一份**，實際生效的是 `~/Library/LaunchAgents/` 裡的副本。
兩邊會漂移，而且 launchd 不會告訴你——所以有 `watch.external_binaries`
在讀實裝的 plist，還有下面那條對帳指令。

## 四個工作

| Label | 什麼時候 | 做什麼 |
|---|---|---|
| `com.kenny.podfetch` | 每天 01:00 | 抓昨夜新集、Gemini 轉錄，寫 `~/podcast-transcripts/<date>/` |
| `com.kenny.kbpublish` | 每 60 秒 | 發布**投顧**：`~/outbox/` → `advisory-rewrite` |
| `com.kenny.kbpublish.podcast` | 每 60 秒 | 發布**podcast**：`~/outbox/podcast/` → `podcast-knowledge-digest` |
| `com.kenny.kbwatch` | 每 4 小時 | 看門狗：Actions 上的哨兵還活著嗎、本機程式有沒有漂移 |

**一個 plist 只發一套系統。** `publish.py` 的參數是 `(outbox, repo, 系統 id)`
三件一組，沒有「多套」這個形態——一次只驗一組檢查、一個目的地，
才不會有「我到底在發哪一套」這個問題。

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

## 已知的坑

- **`kbwatch` 一次只看得了一套系統。** 2026-08-20 之前它指的是 `kb-tracer`，
  於是四條檢查裡有兩條（`sentinel_alive`、`sentinel_verdict`）讀的是靶子的
  heartbeat，另外兩條照常正確——**不會全紅，只會缺一半**，所以撐了兩天沒被發現。
  podcast 的哨兵建好之後要再加一個 `com.kenny.kbwatch.podcast`。
- **`launchd` 的環境是空的**：`PATH=/usr/bin:/bin:/usr/sbin:/sbin`、`cwd=/`。
  所以每個 plist 都明寫 `PATH`、`HOME`、`WorkingDirectory`，程式路徑一律絕對路徑。
- `com.kenny.podfetch` 的 `PATH` 多帶了 `/opt/homebrew/bin`，
  是為了哪天真的裝 ffmpeg 不用改 plist。**ffmpeg 是選配**——
  找不到就走內建切檔，2026-08-20 十集實測全部走 pure-python，沒有一集出問題。
