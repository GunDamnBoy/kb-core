# 文件分工與雙寫

寫東西前對照這份決定放哪一份；第 2 步查漂移時也對照它。

| 檔案 | 只放什麼 | 誰讀 |
|---|---|---|
| `kb-core/podcast/BRIEF.md` | **什麼算對的產出**、當期失敗判準 | 每日排程 |
| `kb-core/podcast/anchors.json` | **每一個數字**：篇幅層級、每集件數、受控詞表、去重、品質門檻、帳本規則 | 每日排程、`checks/podcast.py`、podfetch |
| `kb-core/scripts/podcast/DIGEST-PROMPT.md` | **每天怎麼跑**：順序與分支判斷（**正本**；排程 `SKILL.md` 是它的副本） | 每日排程 |
| `kb-core/scripts/podcast/preamble.md` | **撰寫 subagent 的規則**，派工時整份給它 | 每集的撰寫 subagent |
| `AGENT_BRIEF.md` | **只剩四塊是權威的**：第 1 節節目清單與全文來源（含 A／B 分類與官方稿入口）、第 2 節 podfetch 管線、第 6 節基礎設施、第 8 節變更紀錄。其餘看開頭的失效橫幅 | 維護者；每日排程只在需要 A 類清單時讀第 1 節 |
| `MAINTENANCE.md` | 維護說明、事故檔案（第 7 節）、podfetch 內部設計（第 4C 節）、變更紀錄歸檔（第 11 節）、版本登記簿（第 12 節） | 維護者 |

新的數字寫 `anchors.json`，新的判準寫 `BRIEF.md`，新的流程寫 `DIGEST-PROMPT.md`，
新的撰寫規則寫 `preamble.md`，新的「為什麼」寫 `MAINTENANCE.md` 第 7 節。

> **歸檔的單位是「一場」，不是「一個日曆日」。** 一天常跑兩場以上，照日期比會讓**同日前一場的條目躲過歸檔，brief 第 8 節於是只增不減**。判準是：開工時把不屬於本場的條目全部搬走，同日的前幾場在 `MAINTENANCE.md` 第 11 節用「（同日第 N 批 · 主題）」分隔。

## 規格拆成四份之後

- **改規格之後量一次篇幅**——加完就量，不是等超限才量。
- 四份小檔的風險是**只改其中一份**：四份都短、都好讀，於是沒有人會覺得需要對帳。查漂移時四份一起看。

## 雙寫：現在有三處，一處刻意、兩處是債

**刻意的那處：`preamble.md`。** 撰寫 subagent 讀不到任何規格文件，
所以派工時整份給它。它與 `BRIEF.md`／`anchors.json` 在段數分層、講者紀律、
時間軸旗標、topics 詞表上必然重疊。**改其中任何一項，兩邊都要改。**
（這比上一版的「任務卡」好一點：任務卡是抄在 `SKILL.md` 裡的一段文字，
`preamble.md` 是一個真實檔案，至少 diff 得出來。）

**是債的那處：排程 `SKILL.md` 對 `DIGEST-PROMPT.md` 的整份複製。**
正本在 kb-core，排程那份是副本，**改動一律先改正本再整份貼過去**。
沒有任何機制在維持這件事，所以每場維護都要 `diff` 一次。

**同步是一個時點的事實，本檔只寫「怎麼驗」、不寫「驗過了」。**
驗法：`diff <(cat kb-core/scripts/podcast/DIGEST-PROMPT.md) <(排程那份)`，只差 front matter 五行才算同步。
**排程那份對檔案工具唯讀，沙箱也看不到 `/Users/macmini/Claude/Scheduled/`** —— 排程執行時它會整份出現在
`uploads/SKILL.md`（那就是當天真的跑了什麼），互動場次則 `Read` `list_scheduled_tasks` 回傳的 `path`。

**第二處債：`kb-core/skills/maintain/` 正本 ↔ 已安裝技能副本。**
改維護文件要「改 kb-core 正本 → 整個 `maintain` 目錄打包成 `.skill` → 安裝覆蓋」，
**`save_skill` 只取代 `SKILL.md`、其餘檔案原樣保留，而技能快取是唯讀的**，
所以在工作階段裡改快取那份不會保存、也不會報錯。

**它是三處裡唯一有機械檢查的一處**：`healthcheck.py` 的 `check_skill_copy()` 會逐檔比對並報
WARN。**但那是 WARN 不是 FAIL，而且它只證明「檔案內容不同」，證明不了「哪一份是對的」**——所以看到它要去讀那一檔，
不要預設正本比較新。

## 子代理的視野

外包給子代理的步驟，指示必須自足：子代理讀不到 brief，指向章節對它無效；欄位名要對得上 manifest 的實際欄位（原始連結是 `appleUrl`，不是 `trackViewUrl`）。

> **那組欄位名不是在說 `AGENT_BRIEF.md` 第 1 節寫錯了。** 該節寫的 `trackViewUrl`
> 是 **iTunes Lookup API 的回傳欄位**，manifest 的 `appleUrl` 是 podfetch 落地之後的欄位
> —— 兩個名字各自在自己那一層都是對的。這裡要防的是**拿 API 的欄位名去讀 manifest**。
>
> **另外還有一個 manifest 沒有、但下游一定要有的欄位：`trackId`。**
> `systems/podcast.py` 的 `quote_misses()` 用 `<showKey>-<trackId>.md` 去找逐字稿，
> **找不到就整輪回 `None`，金句閘門會判 SKIPPED —— 也就是開的**
> （`checks/podcast.py` 自己就寫著「這不等於比對過沒問題」）。
> 它由組檔者從 `appleUrl` 的 `?i=` 取出來寫進日期檔，全庫規格一度零記載，08-23 補上。

**還有一件子代理視野的事：`SendMessage` 在排程工作階段不可用。**
交件之後無法追問，要改只能重派一個新的（08-23 為了重挑金句多花 77K token）。
所以派工單要一次給足 —— 這條寫在 `DIGEST-PROMPT.md` 第 3 步。
