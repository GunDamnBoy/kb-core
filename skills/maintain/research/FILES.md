# 文件分工與雙寫

寫東西前對照這份決定放哪一份；查漂移時也對照它。

| 檔案 | 只放什麼 | 誰讀 |
|---|---|---|
| `kb-core/research/BRIEF.md` | **什麼算對的產出**、三層的順序、當期失敗判準 | 每週排程 |
| `kb-core/research/anchors.json` | **每一個數字**：剃除界線、券商與日期辨識、篇幅層級、圖表上限、標籤數、立場帳本到期、已知極限 | 每週排程、`checks/research.py`、`extract.py`、`assemble.py` |
| `kb-core/scripts/research/RUN-PROMPT.md` | **每週怎麼跑**：六步與分支判斷（**正本**；Cowork 排程那份是副本） | 每週排程 |
| `kb-core/scripts/research/preamble.md` | **撰寫 subagent 的規則**，派工時整份給它 | 每份報告的撰寫 subagent |
| `kb-core/chart/anchors.json` 的 `kinds` | **資料形狀 → 圖型**的對照（跟每日五圖共用，這裡讀它不抄它） | `assemble.py`、`dossier.py` |
| `kb-core/research/CHANGELOG.md` | **為什麼這樣改**：決策、事故、被推翻的假設 | 維護者 |
| `kb-core/research/usage-2026-08-22.md` | 首輪用量的完整拆解。**那是建置輪的一次性基線，不是每週報表** —— 每週只留一行進 `kb-core/metrics/usage.csv` | 維護者 |
| `~/broker-research-digest/index.html` | **站台版面**：報告與原句牆兩個分頁 | 瀏覽器 |

新的數字寫 `anchors.json`，新的判準寫 `BRIEF.md`，新的流程寫 `RUN-PROMPT.md`，
新的撰寫規則寫 `preamble.md`，新的「為什麼」寫 `CHANGELOG.md`。

## 雙寫：兩處刻意、一處是債

**刻意的第一處：`preamble.md`。** 撰寫 subagent 讀不到任何規格文件，
所以派工時整份給它。它與 `BRIEF.md`／`anchors.json` 在篇幅層級、原句紀律、
標籤數、圖表上限上必然重疊。**改其中任何一項，兩邊都要改。**

**刻意的第二處：`dossier.py` 的內嵌規格。** 卷宗把機械規則與 `kinds` 對照表
內嵌在最前面，是為了讓子代理不必逆向工程規格（2026-08-22 量到有子代理花了
十輪在找「發布閘門怎麼比對」）。**改 `kinds` 或任何機械規則，卷宗那段要跟著。**

**是債的那處：Cowork 排程那份 prompt 對 `RUN-PROMPT.md` 的整份複製。**
正本在 kb-core，排程那份是副本，**改動一律先改正本再整份貼過去**。
沒有任何機制在維持這件事，所以每場維護都要比一次。

## 跨系統共用的三樣東西

動它們會同時動到別套，改完**兩邊都要驗**：

- **`kb-core/chart/anchors.json` 的 `kinds` 與 `scripts/chart/chartkit.py`** —— 跟每日五圖共用。
  2026-08-22 為了修外資報告的壓字與截斷改了 `chartkit.py`，每日五圖同時吃到。
- **`kb-core/checks/sentinel.py`** —— 門檻現在是 `cadence_hours` 的函數
  （日頻 24、週頻 168，過期倍率 1.5）。上一版是寫死的日頻門檻，
  週頻系統一接上就會天天誤報。**一個對所有系統都一樣的門檻，只是還沒遇到不一樣的系統。**
- **`kb-core/kbcore/system.py` 的 `republish_rule`** —— `frozen` 與 `append_only`
  住在這裡，五套共用。

## 子代理的視野

派出去的步驟，指示必須自足：**子代理讀不到 `BRIEF.md` 也讀不到 `anchors.json`**，
指向章節對它無效。它手上只有兩樣東西 —— `preamble.md` 與 `dossier.py` 產出的卷宗。
欄位名要對得上 `part.json` 的實際欄位，驗收走 `tools/check_part.py`
（它跑的是**跟發布閘門同一套 `_norm`**，不是另一套長得很像的）。
