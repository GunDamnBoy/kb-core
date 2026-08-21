# 排查與稽核

> **這是正本**，`maintain` 技能裡那份是副本。
> 上一版把 `~/.dashpush/repos.txt` 當成推送清單、把 `check_day.py` 當成活的 ——
> 兩者都已退休，殘骸在 `chart-of-the-day/tools/_to_delete/`。

帶著症狀來的分支。第 1 步載入現況之後接這裡，追出結論再回第 3 步報告；
要改東西一律走第 4 步。

## 某天沒產出

排程 `lastRunAt` → 上游當日檔在不在（**`/Users/macmini/advisory-rewrite/data/<日期>.json`**，
讀它的 `stamp`，上游完成時間會漂）→ 預抓狀態檔
`chart-of-the-day/data/_prefetch_status.json` 的 `finished` 與 `ok` → 該日 `about.run`。

**「沒有回執」與「回執說失敗」是兩件不同的事**：前者代表 `publish` 根本沒跑
（或根本沒有草稿），後者代表跑了而被擋。回執在
`~/outbox/chart/<日期>.receipt.json`。

`~/outbox/chart/` 底下有草稿卻沒有回執超過幾分鐘，先看
`~/outbox/chart/publish.log` 與 `launchctl list | grep kbpublish.chart`。

## 發布了但網站沒更新

**這個症狀有兩種，處置完全不同，而回執 `exit 0` 對兩者都會出現** ——
因為它只說到 push 為止。

1. **`data/` 沒上去（推送鏈斷）**：比對
   `chart-of-the-day/.git/refs/heads/main` 與 `.git/refs/remotes/origin/main`。
   不一致＝commit 了但沒推出去。
2. **`charts/` 沒上去（宣告漏了）**：讀 `.git/index` 看
   `charts/<日期>/` 有沒有被追蹤。2026-08-21 就是這一種 ——
   `publish.py` 當時硬寫 `git add "data"`，靜態產出從 08-20 重建後
   就沒有人推過，而 `chart.png_present` 讀的是**本機**檔案系統，全綠。
   現在由 `systems/chart.py` 的 `staged_paths` 宣告、`publish.py` 步驟 4b 對帳。
3. **Pages 打包失敗**：GitHub Actions 上 **8 秒 ＋ exit 1 ＋ 無 artifact ＝ 打包死，
   先找符號連結**（`find . -type l -not -path './.git/*'`，兩個 repo 各跑一次）。
   Node 版本警告是常態雜訊。
4. 抓 `https://gundamnboy.github.io/chart-of-the-day/data/index.json`，
   看 `days[0].date` 與 `updatedLabel` 跟本機比對。
   **`days[0].date` 每天都會是當天**（排程每天都寫），所以只看日期看不出推送鏈斷掉，
   要看 `updatedLabel` 是不是本次執行時間。

## kb-core 的改動沒生效

程式與規格在 `kb-core`，它由 `com.kenny.kbcorepush` 每 300 秒推。
讀 `/Users/macmini/kb-core/.push-receipt.json`：

| `exit` | 意思 |
|---|---|
| 0 | 推上去了 |
| 10 | **閘門擋下**：`py_compile` 或檢查自檢有紅字，看 `detail` |
| 15 | 分岔 origin —— 刻意不自動 rebase，要人看 |
| 沒有回執 | 這一支根本沒跑，看 `~/outbox/kbcorepush.log` 與 launchctl |

工作區改動不到 5 分鐘時它會刻意跳過（靜置閘門），log 會寫出來。

## 數字被質疑

該日 JSON 的 `series` 有完整資料點（欄位是 `dates`／`values`），直接重算；
歷史錨點也應可從序列重算。**序列快取在
`chart-of-the-day/data/series/<id>.csv`**，檔頭記著來源與抓取日期。

比對時注意代理：`^SOX` 用 `SOXQ`、`BZ=F` 用 `DCOILBRENTEU`、
`GC=F` 用 `GLD`（含年化約 0.4% 管理費耗損，水準不等於每盎司金價）。
對照表在 `anchors.proxies`，歷史深度限制在 `anchors.history_limits`
（BAML 只有近三年、SOXQ 只回到 2021 —— **不可寫「歷史上」或「十年分位」**）。

## QA 旗標

分類法與門檻以 `kb-core/chart/anchors.json` 的 `quality` 為準（5σ，
**不要退回 6σ**，那是覆核逼出來的校準值）。
四種處置：真實事件／轉倉／錯價／衍生序列的窗口效應。

**先看幅度再看故事**：轉倉價差正常在 1% 以內，所以「跌 11% 是轉倉」
在數量級上就不成立。低水準序列（BAML 利差約 2%）的百分比變動會被基期放大，
換算成基點再判。

`chart_verify` 的紅字與該日 `about.qa_disposition` 對照著看。

## token 稽核

量測「必讀 vs 維護才讀」的分類與每日手寫量，對照 `chart/CHANGELOG.md`
的量測紀錄與歷份 `TOKEN_AUDIT_*.md`。
`series_spec` 的存在就是為了這件事：執行者決定畫什麼，不抄寫資料點。
優化落地後請使用者於次日執行後索取當期執行報告驗收。
