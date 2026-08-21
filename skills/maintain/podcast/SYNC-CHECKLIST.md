# 同步比對清單（子代理任務）

第 2 步用。逐區比對，每區給結論（相符／不一致／不適用）；不一致處指出**行號與原文**。產出就是這份不一致清單本身，不附改進建議。

對照檔：`~/podcast-knowledge-digest/AGENT_BRIEF.md`（**先確認它開頭有沒有失效橫幅** —— 見 `MAIN.md` 開頭的待查項；有的話權威在 `kb-core/podcast/`）、排程 **`podcast-daily-300`** 的 `SKILL.md`（路徑由主線提供）、`~/podcast-knowledge-digest/data/observations.json`、README。任務卡與 brief 的雙寫關係見 [`FILES.md`](FILES.md)。

## brief ↔ 排程 SKILL.md

- 執行時刻（podfetch 01:00／日報 03:00／pmset 00:55）
- 節目數量與 showKey 鍵值——「N 檔」這個數字也要查 README，healthcheck 看不到它
- 全文取得的退援順序：**四層**，FT 是第 1 層官方稿的特例、不是獨立層；「>120 分鐘的 A 類直接用 podfetch 稿」這條要在 brief 第 1／2 節與任務卡三處都在
- 去重規則：跨日與**同日同源**（manifest 原文 `title` ＋ `durationMs` 兩者都同才合併、`show_priority` 決定保留誰）
- 內容規格：段數分層、字數的唯一定義、下界例外、金句與核心重點條數、交叉觀察門檻（以去重後集數計）、**topics 詞表逐字逐序比對**（最容易錯）、`guests`／`quality` 欄位。權威數字在 brief 第 3／4 節，任務卡是抄過去的那一份
- **三種品質旗標**：`warnings`（決定 status）／`speakerNotes`／`timestampNotes` 三個維度的分工，任務卡是否都講到
- 子代理門檻、工具呼叫預算、中斷重派的成本門檻（數值以 brief 為準）
- **觀察點記分板三邊**：brief 第 4 節格式 ↔ SKILL.md 第 4 步回訪指示 ↔ `data/observations.json` 實檔欄位
- 外包給子代理的步驟，指示是否自足（判準見 `FILES.md`「子代理的視野」）
- brief 宣稱「已同步進 SKILL.md」的項目，SKILL.md 裡真的有嗎——紀錄與實況會脫鉤，而紀錄看起來更可信

## brief 內部自我一致性

- 同一數值在不同段落是否打架
- 標題宣告的數量與實際條目數是否相符
- 「現有值」「目前定義了 N 組」是否還反映實情
- 跨檔引用有沒有斷鏈，章節號也要核
