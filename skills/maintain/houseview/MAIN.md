# 國際市場 Houseview · 草稿機維護（v3 體例）

每月產出一份 18–22 頁的 pptx **初稿**（v3 外資投行體例，2026-08 起），供台新投顧全策組接手。成功定義：同仁拿到後是**補圖與改字**，不是重做。

版本與數值一律以現場讀到的 `healthcheck_hv.py` 與 `HOUSEVIEW_BRIEF.md` 為準——這份維護文件自己就曾經因為描述停在 v1 而差點誤導維護。

全程繁體中文（台灣用語）。repo 根目錄 `~/houseview`（沙箱路徑通常是 `/sessions/<name>/mnt/houseview/`，腳本自動偵測）。

## 硬規矩

- **手動啟動、沒有排程**：每月產出時間由使用者決定，要跑就把 brief 第 7 節整段貼給 Claude。healthcheck 有反向守門——brief 被寫回 cron／排程字樣會 FAIL。`list_scheduled_tasks` 若出現 Houseview 排程，那本身就是異常，回報使用者。
- **在 `~/chart-of-the-day` 看檔案狀態用 `cat`／`ls`／`grep`**：dashpush 每 180 秒自動推送，任何 git 指令（含 `git status`）留下的 index.lock 都會擋住它。`~/houseview` 不在推送清單（`cat ~/.dashpush/repos.txt` 確認）、git 安全。
- **「怎麼倒回去」以 `git-init.sh` 已在 Mac 上跑過為前提**（沙箱做不到）；跑過之前，所有 git 回退指令都是空話。每次維護提醒一次。

各檔的權威範圍、上游依賴、v3 體裁與改動要保住的不變量在 [`FILES.md`](FILES.md)：第 2 步比對、排查版面問題、或動手改任何東西之前讀。

## 第 1 步：載入現況

1. 兩期別各跑一次健康檢查：

   ```
   python3 ~/houseview/healthcheck_hv.py --content content-2026-08-skeleton.json.example --quiet
   python3 ~/houseview/healthcheck_hv.py --content content-2026-07.json --quiet
   ```

   第一條驗 v3 骨架——骨架檔副檔名 `.json.example`，**不在預設 glob 內，必須用 `--content` 指名**；不帶參數時 glob 只會撿到 legacy 的 `content-2026-07.json`，兩條就變成同一條，期別分流等於沒測到。第二條驗 legacy 不回溯。
2. 讀 `HOUSEVIEW_BRIEF.md` 全部（特別是第 1 節縱深寫法與第 6 節鐵律）；`CHANGELOG.md` 讀最新一兩節，含指標軌跡表。
3. 列出 `content-*.json`，看最近期別的章節組成與真圖比例。

判讀健康檢查輸出：2026-08-13 v3.1 的基準是 v3 骨架 59/0/0、2026-07 為 52/2/0（與 CHANGELOG 指標軌跡表最新一列不同時，以軌跡表為準）。2026-07 那兩條 WARN（圖表密度 1.00、焦點頁無 verdict）是已知歷史狀態，維持原狀。新出現的 FAIL／WARN 全部帶進報告。

完成條件：兩期別的健康檢查輸出、brief 全文、CHANGELOG 最新一兩節、最近期別的章節組成，四項都有實際輸出在手，沒有一項靠記憶或推論。

## 第 2 步：找漂移

系統的每個意義都有**單一來源**：規格在 brief、每月流程在 brief §7 prompt、結構檢查與渲染在 `build_hv3.js`、唯讀驗收在 `healthcheck_hv.py`、歷史在 CHANGELOG。**漂移**＝某個意義偷偷長出第二份，或一組本該同步的多份只跟上了一份。

派**子代理獨立比對**——歷次維護子代理都抓到主線漏掉的實質矛盾。子代理回報的引句**逐條回查原文再採信**：曾有一半的「原文」引句在檔案裡根本不存在。

逐項查，每項給出「相符／漂移／不適用」，判為漂移的要指出兩邊差在哪：

- **brief 內部**：§1 版面與縱深規則 vs §6 鐵律；§2 章節規則 vs §7 步驟；待決事項是否已解決沒刪
- **brief ↔ §7 prompt**：十五章清單、頁序四不變量、縱深九手法名單、「查無就寫查無」鐵律（含歷史數字）、焦點四條件、圖表三來源策略、驗證三項
- **三處一組**（改 schema 最容易只跟上一處）：brief §8 schema ↔ `build_hv3.js` 的 validateContent／NEED／RENDER ↔ `healthcheck_hv.py` 的 payload 檢查
- **期別分流**：新增規則是否 gate 在 ≥2026-08，legacy 期別是否仍綠
- **跨 repo 配色**：healthcheck 比對 `~/chart-of-the-day` 的 ACCENT 是否仍為 #D70C18

完成條件：五個面向逐項有結論，子代理引的每一句都回查過原文。

## 第 3 步：報告現況，再問要改什麼

報兩期別健康檢查結果（含新出現的 FAIL／WARN）、最近期別的章節組成與真圖比例、第 2 步的漂移清單、CHANGELOG 待決事項。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認。這一步的產出是報告與那句話，不是任何檔案修改。

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走——改哪個檔、三處一組的連鎖點、CHANGELOG 五欄與 commit／tag，以及改完必須全數通過的驗證清單（含轉 PDF 逐頁看圖）。
