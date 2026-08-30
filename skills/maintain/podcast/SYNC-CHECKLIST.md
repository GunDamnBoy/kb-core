# 同步比對清單（子代理任務）

第 2 步用。逐區比對，每區給結論（相符／不一致／不適用）；不一致處指出**行號與原文**。產出就是這份不一致清單本身，不附改進建議。

> **2026-08-23 改寫。** 上一版停在 08-21，沒有跟上 08-22 的拆檔：它還在講「brief 第 3／4 節」與「任務卡」，而數字早就搬進 `anchors.json`、任務卡早就變成 `preamble.md`。
> 登記簿 08-22 那一列動的是 `{MAIN,FILES,MODIFY}.md` —— **四份改了三份，而漏掉的正是這份用來查漂移的清單。**
> 於是下一場維護會照著過期的清單去查漂移，**而清單自己就是漂移。**

## 先確認權威落在哪裡

**「brief」這個詞在拆檔之後指兩份不同的檔，比對前先分清楚：**

| 要查什麼 | 現在的權威 |
|---|---|
| 什麼算對的產出、當期失敗判準 | `kb-core/podcast/BRIEF.md` |
| **每一個數字**（篇幅層級、每集件數、受控詞表、去重、品質門檻） | `kb-core/podcast/anchors.json` |
| 每天怎麼跑（流程與分支） | `kb-core/scripts/podcast/DIGEST-PROMPT.md`（**正本**） |
| 撰寫 subagent 的規則 | `kb-core/scripts/podcast/preamble.md` |
| **節目清單與 A/B 分類、官方稿入口** | `AGENT_BRIEF.md` **第 1 節** |
| podfetch 管線讀法、基礎設施備忘、變更紀錄 | `AGENT_BRIEF.md` 第 2／6／8 節 |
| 發布前檢查 | `kb-core/checks/podcast.py`＋`systems/podcast.py` |

**`AGENT_BRIEF.md` 開頭掛著 2026-08-21 的失效橫幅，只剩第 1／2／6／8 節權威**，其餘一律以 kb-core 為準。**但「已降級」不等於「可以放著爛」** —— 08-23 就在第 6 節（權威區）抓到兩處硬錯：一支已退場的推送者、一份少了兩個資料夾的連線清單。**權威區的錯誤比降級區嚴重，優先查它。**

對照檔還有：排程 **`podcast-daily-300`** 的 `SKILL.md`（沙箱看不到 `/Users/macmini/Claude/Scheduled/`，要用 `Read` 讀 `list_scheduled_tasks` 回傳的 `path`；排程執行當下它會整份出現在 `uploads/SKILL.md`）、`data/observations.json`、`README.md`。

## 正本 ↔ 副本（**有兩組，不是一組**）

**2026-08-30 補**：本節原本只講 `DIGEST-PROMPT` ↔ 排程 `SKILL.md`，而 08-24 起還有第二組
—— **`kb-core/skills/maintain/` 正本 ↔ 已安裝的技能副本（27 個檔）**。
第二組有機械檢查（`healthcheck.check_skill_copy()`，WARN 級），第一組沒有。
**改了 kb-core 那份正本之後，`check_skill_copy` 會一直報不一致，直到整個 `maintain`
目錄重新打包成 `.skill` 並由使用者安裝覆蓋**（`save_skill` 只換得掉 `SKILL.md`、動不到附屬檔）。
所以動技能正本的那一場，**收工前要交付 `.skill` 檔，否則下一場會看到一個不知從何而來的 WARN**。

### 第一組：`DIGEST-PROMPT.md` ↔ 排程 `SKILL.md`

**這是唯一一處整份複製，也是最會出事的一處。**

- `diff` 正本與副本，**只差 front matter 五行才算同步**。行數關係：副本 ＝ 正本 ＋ 5。
- **不要接受文件裡任何「目前同步」的宣稱當證據** —— 08-22 `FILES.md` 寫了「實測只差 front matter」，而那是 06:41 量的，正本 11:59 又改了，副本整整少了一節（第 199–217 行的用量指示），**沒有人回頭改那句話**。實害：兩輪都照舊版填了自述值，`eff_tokens_k` 因此有 4913／235／276 三個相差 20 倍的值。
- 副本缺一整節時，**症狀是「執行者照舊版做事」而不是報錯**。所以要比對的是內容，不是「有沒有人說過同步」。
- **漂移可以是雙向的，不要只查「副本少了什麼」**（2026-08-30 新增）。那天正本 292 行、副本 308 行，
  **兩邊各缺一塊**：正本有一段 08-23 之後的訂正副本沒有，副本有一整段「不要抄自述值」的警告正本沒有，
  而且**同一節的結論相反**（正本「搆得到了」／副本「搆不到」）。**行數對不上時先算偏移**：
  在數個分散錨點確認偏移恆為 +5，分歧就會被夾出來。
- **正本自己也可能打架。** 同一次還抓到正本的節標題（「這一輪量不到，所以不要填」）
  與六行之下的內文（「搆得到了，這一段的結論已經過期」）直接相反 ——
  **在正本上打補丁而不改標題，會讓副本的維護者不知道該同步哪一句。**
- **哪一份是對的要去查，不要預設正本贏。** 08-30 那次是查了 `kb-core/metrics/usage.csv`
  有沒有 podcast 的列、沙箱裡有沒有 `.claude/projects` 之後才確認正本是對的
  —— **兩份相反時，兩份都可能是舊的。**

## 規格四份之間

**拆檔之後的失效形態是「只改其中一份」，所以四份要一起看。**

- **執行時刻**：`anchors.schedule`（wake 00:55／podfetch 01:00／digest 03:00／`official_transcripts` 應為 `null`）↔ `AGENT_BRIEF` 第 0 節時序表 ↔ 實查 `list_scheduled_tasks` 的 `cronExpression`
- **節目數量與 showKey**：`shows.json` ↔ `README` 的「N 檔」與追蹤清單 ↔ `AGENT_BRIEF` 第 1 節的 A 類表。**README 內部也要自我核對**（08-23 抓到它的 A 類清單含已除役的 Lex Fridman，與同檔追蹤清單矛盾）
- **退援四層**：順序、FT 是第 1 層特例不是獨立層、FT 失效退回第 2 層不跳 YouTube，**以及「>120 分鐘的 A 類直接用 podfetch 稿」** —— 這一條要在 `anchors.fallback_order`、`AGENT_BRIEF` 第 1／2 節、**`DIGEST-PROMPT` 第 1 之二步**都在（08-23 補上流程正本那一處；在此之前每天唯一講「A 類怎麼辦」的那段文字裡沒有它）
- **去重**：`anchors.dedup`（`title` ＋ `durationMs` 兩者都同才合併、`require_both`、`keep_by`、`⚠︎` 佔位不算已收錄）↔ `DIGEST-PROMPT` 第 2 步 ↔ `checks/podcast.py` 的 `_no_dupes`（應從 anchors 讀，不寫死）
- **內容規格**：`anchors.length_tiers` ＋ `_length_tiers_rules` ＋ `per_episode` ↔ `BRIEF` 第四／五節 ↔ `preamble` 第一節 ↔ `checks` 的 `chars_in_tier`。**`topics` 詞表要逐字逐序比對**（最容易錯）
- **日期檔的欄位形狀**：`BRIEF` 第二節的清單 ↔ `data/<date>.json` 實檔 ↔ `systems/podcast.py` 實際讀的欄位。**這一區 08-23 抓到三處**：`quotes[]` 寫成 `speaker` 而實檔是 `by`、`trackId` 與 `minutes` 兩個必要欄位不在清單裡。**`trackId` 缺席的後果是金句閘門判 SKIPPED —— 安靜地開著。**
- **三種品質旗標**：`anchors.quality.note_dimensions` 的分工（`warnings` 決定 status／後兩者不影響）↔ `preamble` 第五、九節 ↔ **`DIGEST-PROMPT`**（組檔者要產出 `quality{}` 四個子欄位，而流程正本一度全文沒提過它們 —— **規則的執行者不是規則的讀者**）
- **觀察點記分板四邊**：`BRIEF` 第八節 ↔ `anchors.observations` ↔ `DIGEST-PROMPT` 第 5 步 ↔ `data/observations.json` 實檔欄位（`id/date/text/status/verdict/verdictDate/due`）
- **外包給子代理的指示是否自足**（判準見 `FILES.md`「子代理的視野」）。`preamble` 自稱「這裡就是全部的規則」，**核對它是不是真的**

## 每一份的內部自我一致性

- 同一數值在不同段落是否打架
- **標題或敘述宣告的數量 vs 實際條目數**（08-23 抓到 `checks/podcast.py` 檔頭寫「這十條」而 podfetch suite 實為 11 條）
- **「現在只有 X，還沒有 Y」這類階段性敘述是否還成立**（同上檔頭有一整節寫「為什麼現在只有取數層，沒有日報層」，而同一個檔案第 572 行以下就是日報層 —— **判斷是對的、兌現了，但沒有人回頭刪那一節**）
- **「由某某負責／由哨兵處理」這類宣稱，去確認某某真的在跑**（08-23 抓到 `BRIEF` 第八節「判定到期由哨兵開 issue」，而 `sentinel/report.md` 印的是 ⏭️ 未執行，且帳本形狀與它不相容）
- **自我指涉的數字有沒有標時點**（`BRIEF` front matter 的字元數、`anchors._due_note` 與 `checks` 裡的「N 條裡 M 條」）
- 跨檔引用有沒有斷鏈，**章節號也要核**（08-23 抓到 `AGENT_BRIEF` 開頭指的「第 3 步／第 5.5 步／第 6 步」三處內容全部不存在，`anchors.fetch_limits.subagent_threshold_kb` 全庫零讀者）

## 這份清單自己

**比對完順手看一眼本檔的 mtime 與 `MAIN.md`／`FILES.md`／`MODIFY.md` 差多少。** 差太多就是它又落後了 —— 08-23 那次差了一整天又半個系統。**用來查漂移的東西自己漂了，是最難發現的一種，因為沒有人拿它去查它自己。**

**它 08-30 又被抓到落後一場**：08-24 新增了 `check_skill_copy()` 這一整組正本↔副本關係，
而本檔那一區一個字都沒提（已於同日補上）。**同一個形態連續兩次，所以把它從叮嚀改成條件**：
**mtime 比 `MAIN.md`／`MODIFY.md` 舊，就先讀第 12 節登記簿最新那一列，
確認那一場有沒有新增「需要比對的東西」。** 光比 mtime 只知道它舊了，不知道舊掉的是哪一塊。
