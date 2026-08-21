# 執行修改

> **這是正本**，`maintain` 技能裡那份是副本。
> 上一版停在 2026-08-20 重建之前，表格裡半數的檔案路徑已經不存在。

第 4 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。**

## 改哪裡

所有路徑相對於 `/Users/macmini/kb-core`，除非另有標明。

| 要改的東西 | 動這個檔 | 連帶 |
|---|---|---|
| 圖表樣式／加圖型 | `scripts/chart/chartkit.py`，**兩軌同時** | 重跑 `render_day.py <最近一天>` 並**實際看圖**；新圖型當天一定要實載網頁看一眼 |
| 資料源 | `scripts/chart/fetch.py`（美股與 FRED）、`fetch_twse.py`／`fetch_tw_price.py`（台股） | 在 `chart/SOURCES.md` 登錄，實測後把限制寫下來；限流與代理的數字進 `chart/anchors.json` |
| 序列轉換 | `scripts/chart/build_series.py` 的 `_transform`（唯一實作） | 跑 `--selftest`；`macro_release.py` 轉呼叫它，不必另改 |
| 預抓清單／時刻 | `scripts/chart/prefetch.py` | 時刻要跟 `anchors.schedule.prefetch` 與 `launchd/com.kenny.kbprefetch.chart.plist` **三者一起動** |
| 檢查規則 | `checks/chart.py` | **數字不寫在這裡**，一律從 `chart/anchors.json` 讀；新硬規則帶生效日；動到 fixture 要確認它用的是**真實資料形狀** |
| 門檻與每一個數字 | `chart/anchors.json` | 該數字的所有讀者（檢查、取數層、渲染層、SKILL）都要回頭確認 |
| 什麼算對的產出 | `chart/BRIEF.md` | 有數字就指路到 anchors，不抄值 |
| 每天怎麼跑 | `skills/chart/SKILL.md`（正本） | 排程 prompt 整份取代，見下 |
| payload 形狀／要推哪些路徑／index entry | `systems/chart.py` | 新增維度要先加進 `kbcore/system.py` 的 `System` |
| 發布流程 | `tools/publish.py` | 三套系統共用，**改它等於同時改三套**；exit 碼表在 `kbcore/result.py`，動它要連 SKILL 與排程 prompt 的處置表 |
| kb-core 自己怎麼推 | `tools/push_kbcore.py` ＋ `launchd/com.kenny.kbcorepush.plist` | `QUIET_MINUTES` 與 plist 的 `StartInterval` 是一組的 |
| schema 或欄位名 | 產生端 | `chart-of-the-day/index.html`（動態渲染，加 theme 不用改、改欄位名才要）；`days[0].date` 與 `days[0].headline` 兩個鍵保留給姊妹庫 |

**不要改 `chart-of-the-day/AGENT_BRIEF.md` 或 `MAINTENANCE.md`。**
兩份都掛著「2026-08-20 起不再是權威」的橫幅，留著只是為了還沒搬完的事故紀錄。
改沒在跑的那一份不會有任何徵兆。

## 排程 prompt

`mcp__scheduled-tasks__update_scheduled_task` 是**整份取代**：
先 Read 現有全文，漏帶的段落等於刪除。歷次實測教訓原樣留著。
先改 `skills/chart/SKILL.md` 正本，再整份貼過去。

## 變更紀錄制度

1. 新版本寫進 `chart/CHANGELOG.md` **最上面**，五欄結構：
   動到哪些檔／量測／怎麼驗的／怎麼倒回去／當時已知的風險。
2. 量測值當場量，估算標 `~`；更正舊值要留痕，不靜默改寫。
3. 事故要寫成「它當初藏住的方式」，不只寫「修好了」——
   `anchors.rendering.drift_assertions` 是這種寫法的樣板。
4. 做完 token 類優化，請使用者於次日執行後索取當期執行報告驗收。

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步，不要往下走。
每一項都看完整輸出與 exit code。

```bash
cd /Users/macmini/kb-core && python3 -m py_compile tools/*.py checks/*.py systems/*.py kbcore/*.py scripts/chart/*.py
```

- 檢查自檢（fixture 與 near_miss 兩側）0 失敗：
  `python3 -c "import sys;sys.path.insert(0,'.');import checks,systems;from kbcore.report import selftest;d=selftest();print(len(d));[print(x) for x in d]"`
- `python3 scripts/chart/build_series.py --selftest`
- `python3 tools/chart_verify.py /Users/macmini/chart-of-the-day` 對最新一期
  沒有非預期的 FAIL；改了檢查規則就確認它報的是**預期的那幾筆**，
  並拿一期舊封存回測看它有沒有反應。
- 既有 `chart-of-the-day/data/*.json` 全部可 `json.load`。
- `chart/anchors.json` 可 `json.load`。
- `index.html` 抽 `<script>` 後 `node --check`。
- 兩個 repo 各跑 `find . -type l -not -path './.git/*'`，歸零。
- 改過 `chartkit` → 重跑 `render_day.py` 最近一天，**實際看圖**
  （渲染類 bug 跑得動、看不出來）。
- 改過 `publish.py` 或 `staged_paths` → **在 `/tmp` 另建 bare origin ＋ 工作 repo
  跑一次端到端**，確認宣告的路徑真的進了遠端。不要拿真 repo 試。
- `chart/CHANGELOG.md` 已加新版本。
- 同步組（`skills/chart/SKILL.md` 正本、排程 prompt、`skills/maintain/chart/*.md`
  與技能裡的副本）逐項對過。
