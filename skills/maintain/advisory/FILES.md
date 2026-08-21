# 檔案地圖與權威範圍

第 1／2 步查漂移時對照用。標**唯一權威版本**的檔案沒有副本——任何看起來像副本的東西就是漂移。

| 檔案 | 角色 |
|---|---|
| `AGENT_BRIEF.md` | 執行規格（1～7 節），每日排程第 0 步完整讀 |
| `CHANGELOG.md` | 版本總覽表＋逐版明細。每日排程不讀，維護時讀 |
| `scripts/check.py` | 發布前檢查的**唯一權威版本**（QUOTA／WEEKEND_QUOTA／SRCOK／DEDUP_EXEMPT 四張表）。出口碼 0＝通過；自動判定平日／週末模式 |
| `scripts/metrics.py` | 歷史指標：跨版趨勢（含 thermo 溫度欄）、各組緩衝（週末感知）、來源貢獻矩陣。`--tags` 標籤動能、`--pulse` 五資產立場歷史、`--csv` 匯出 |
| `scripts/read_article.js` | 標準文章讀法的**唯一權威版本** |
| `scripts/list_timestamps.js` | 列表頁預篩的**唯一權威版本**（DOM 四層備援含 `__NEXT_DATA__`；查詢字串帶 ID 視為單篇） |
| `scripts/subagent_preamble.md` | 採集員共用前言：讀法、各來源眉角、發稿日曆、黑名單、探針策略、合規、回報格式 |
| `prompts/YYYY-MM-DD-v{N}.md` | 排程 prompt 的存檔副本（正本不在 repo、不在 git） |
| `index.html` ＋ `data/*.json` | 前端外殼＋每日封存（每日 JSON 就是那天的完整快照） |
| `data/index.json` | 封存索引＋跨日記憶：每日 entry 帶 `thermo`／`threads`／`watch`／`pulse`／`snap` 五欄位，被 writer、check.py、前端三方讀 |

`search.html` 是純前端搜尋頁，只有 BADGE 表需要跟著來源異動走。

## subagent 的視野

採集 subagent **只讀** `subagent_preamble.md` ＋ `read_article.js` ＋ `list_timestamps.js`，主 agent 每天三份逐字轉發，缺一不可（brief 第 5 節）。它讀不到 brief——**眉角類知識放 preamble，不放 brief**。

## 系統形狀

每天一個獨立 JSON 封存，只收滾動 24 小時窗口內發布的新聞，100% 當天新寫，15 個子類別各有分級下限（權威數字在 `check.py` 的 `QUOTA`／`WEEKEND_QUOTA`，此處不重述）。v17 起有時間序列欄位（thermo 整數、snap num/chgPct、卡片 thread），v18 起有判斷欄位（五資產 pulse、昨日節點回顧 watchReview）。對照台新 House View 章節；下游是 convergence-weekly 與每月 House View，可直接吃 pulse／thermo／thread 序列。
