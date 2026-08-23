# 執行修改

> **這是正本**，`maintain` 技能裡那份是副本。
> 上一版停在重建之前：表格裡的 `AGENT_BRIEF.md`、`scripts/check.py`、
> `scripts/metrics.py`、`search.html` 在現行佈局裡**都不存在**，
> 驗證清單裡的兩行指令跑不動。

第 4 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。**

## 改哪裡

除非另有標明，路徑相對於 `/Users/macmini/kb-core`；
資料 repo 是 `/Users/macmini/advisory-rewrite`。

| 要改的東西 | 動這個檔 | 連帶 |
|---|---|---|
| 每一個數字（下限、家數、篇幅、窗口） | `advisory/anchors.json` | 該數字的所有讀者都要回頭確認；**`groups` 動到就會讓五圖的 `chart.theme_unique` 變紅** |
| 什麼算對的產出 | `advisory/BRIEF.md` | 有數字就指路到 anchors，不抄值 |
| 檢查規則 | `checks/advisory.py` | **數字不寫在這裡**，一律從 anchors 讀；動到 fixture 要確認它用的是**真實資料形狀** |
| payload 怎麼組／index entry／要推哪些路徑 | `systems/advisory.py` | 新增維度要先加進 `kbcore/system.py` 的 `System` |
| 採集眉角、黑名單、發稿日曆 | `scripts/advisory/preamble.md` | 無 |
| Actions 保底層（兩條 OAS、黃金持倉、台股端點） | `tools/fetch_advisory.py` | 路由表在 `kbcore/fetch_tw.py` 的 `ROUTES` |
| 每天怎麼跑 | `skills/advisory/SKILL.md`（正本） | 排程 prompt 整份取代，見下 |
| 排程與 launchd | `launchd/*.plist`＋包裝腳本＋`launchd/README.md` 的表 | 新增 Label 要同時登記進 `kbcore/env.py` 的 `REQUIRED_BY_LABEL`，**否則 `watch.external_binaries` 會 FAIL，而 FAIL 的看門狗不更新 heartbeat** —— 2026-08-23 `kbpublish.bubble` 就是這樣讓哨兵停在前一天。裝到 `~/Library/LaunchAgents/` 是**機器上的手動步驟**，工作階段做不到 |
| 發布流程 | `tools/publish.py` | **三套系統共用，改它等於同時改三套** |
| 網站呈現 | `advisory-rewrite/index.html` | 徽章表從檔案實際解析比對。**2026-08-22 起它在 `staged_paths` 裡，改了會自動上線** —— 在那之前不會，而回執照樣 exit 0（見 CHANGELOG 該日第一節）。代價是**沒有任何檢查在看外殼**：改壞了會直接上線。改完至少要抽 script 跑 `node --check`，視覺請人工確認（`file://` 沒有自動路徑） |

**不要改舊 checkout `~/advisory-knowledge-hub` 裡的任何東西。** 它已於 2026-08-21 搬到 `~/_to_delete/advisory-knowledge-hub-stale-20260818`。
那份停在 2026-08-18，改它不會有任何徵兆，也不會有任何效果。

## 排程 prompt

`mcp__scheduled-tasks__update_scheduled_task` 是**整份取代**：
先 Read 現有全文，漏帶的段落等於刪除。
taskId 是 **`advisory-daily-0730`**。
先改 `skills/advisory/SKILL.md` 正本，再整份貼過去。

## 來源異動

- **新增**：`index.html` 的徽章表 ＋ `scripts/advisory/preamble.md` 的發稿日曆。
- **移除**：CSS 與 BADGE 對照表保留（歷史封存要渲染），只從顯示列拿掉；
  **`preamble.md` 黑名單加一行** —— 這行比從清單刪掉更要緊。

## 收尾

1. `advisory/CHANGELOG.md` **最下方**加一筆，五欄結構：
   動到哪些檔／量測／怎麼驗的／怎麼倒回去／當時已知的風險。
   （這一行 2026-08-22 之前寫的是「最上方」，與檔案實際慣例相反 ——
   `維護判斷` 那一節在最上面、逐版明細**由舊到新往下排**，08-19／08-20／08-21 三筆都是這樣。
   照舊的寫法做會把新的一筆插進維護判斷與最早那一筆之間。）
2. 量測值當場量，估算標 `~`；更正舊值要留痕，不靜默改寫。
3. 事故要寫成「它當初藏住的方式」，不只寫「修好了」。

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步，不要往下走。
每一項都看完整輸出與 exit code。

```bash
cd /Users/macmini/kb-core && python3 -m py_compile tools/*.py checks/*.py systems/*.py kbcore/*.py
```

- 檢查自檢（fixture 與 near_miss 兩側）0 失敗：
  `python3 -c "import sys;sys.path.insert(0,'.');import checks,systems;from kbcore.report import selftest;d=selftest();print(len(d));[print(x) for x in d]"`
- `python3 tools/advisory_verify.py /Users/macmini/advisory-rewrite /Users/macmini/advisory-rewrite/data/<最新日期>.json`
  沒有非預期的 FAIL。改了檢查規則就確認它報的是**預期的那幾筆**，
  並拿一期舊封存回測看它有沒有反應。
  （2026-08-05 之前的歷史檔用現行十五組下限量會失敗，屬預期，不是回歸。）
- `advisory/anchors.json` 可 `json.load`。
- 既有 `advisory-rewrite/data/*.json` 全部可 `json.load`。
- `advisory-rewrite/index.html` 抽 `<script>` 後 `node --check`；
  徽章表從檔案解析比對。
- **動到 `groups` 時，回頭跑一次五圖的檢查**：
  `python3 tools/chart_verify.py /Users/macmini/chart-of-the-day`
  —— `chart.theme_unique` 直接讀這份 `groups`，改組名會讓那邊變紅。
- 資料 repo 內 `find . -type l -not -path './.git/*'` 歸零。
- 改過 `publish.py` 或 `staged_paths` → **在 `/tmp` 另建 bare origin ＋ 工作 repo
  跑一次端到端**，確認宣告的路徑真的進了遠端。不要拿真 repo 試。
- `advisory/CHANGELOG.md` 已加新版本。
- 同步組（`skills/advisory/SKILL.md` 正本、排程 prompt、
  `skills/maintain/advisory/*.md` 與技能裡的副本）逐項對過。
