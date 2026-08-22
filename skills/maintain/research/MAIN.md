# 外資報告週摘 · 維護

> **這是正本**，`maintain` 技能裡那份是副本。
>
> 這一套 2026-08-21 建立、08-22 上線，是四套活的系統裡**唯一週頻的**。
> 它撞破過三個原本寫成通則的假設（哨兵門檻、不可改寫守衛、路徑展開），
> 每一個都在下面的硬規矩裡。

全程繁體中文（台灣用語）。

| | |
|---|---|
| 素材與中間檔 | `~/broker-research`（**不在任何 repo 裡**） |
| 資料 repo | `~/broker-research-digest` |
| 站台 | <https://gundamnboy.github.io/broker-research-digest/> |
| 排程 | Cowork 排程「外資報告週摘（週日深夜）」`0 15 * * 0`（週日 23:00 台北） |
| 發布 | `com.kenny.kbpublish.research`（每 60 秒） |
| 哨兵 | GitHub `sentinel.yml`（週二 11:00 台北）＋ `com.kenny.kbwatch.research`（12 小時） |

## 硬規矩

- **原文與抽取文字永不進任何 repo。** 報告逐頁蓋有可追溯到個人的浮水印
  （公司信箱＋追蹤雜湊），在抽取的第一步就剃掉。這條界線是**結構性的**
  —— 那些檔案住在所有 repo 之外，不是靠 `.gitignore`。
  上網的是精華、原句、標籤與重製圖。

- **路徑只有一個家：`BROKER_RESEARCH_ROOT`。**
  `~` 在 Mac 的 launchd 展開成 `/Users/macmini`，在 Cowork 工作階段的
  device bash 展開成那個階段的沙箱家目錄。2026-08-22 這件事一天內咬了三次，
  最糟的兩次是：`extract.py` 回報「18 份抽取完成」寫進沙箱、
  `build_index.py` 說「空輪次」而 inbox 裡有 18 份 ——
  **它們的輸出讀起來完全正常。** 理由與三次的樣子寫在
  `kb-core/scripts/research/_paths.py` 的檔頭。

- **不跑任何 git 指令**（含 `git status`）。`com.kenny.kbpublish.research`
  每 60 秒動一次，`.git/index.lock` 會擋住它。要看推送鏈就 `cat`
  `.git/refs/heads/main` 與 `.git/refs/remotes/origin/main` 比對。

- **不刪除使用者機器上的檔案**（device bash 也刪不掉）。要清的東西 `mv`
  進同一個掛載資料夾底下的 `_to_delete/` 並回報。

- **每個意義各有單一來源**：什麼算對的產出在 `kb-core/research/BRIEF.md`、
  每一個數字在 `kb-core/research/anchors.json`、每週怎麼跑在
  `kb-core/scripts/research/RUN-PROMPT.md`、撰寫規則在 `preamble.md`、
  圖型與欄位對照在 **`kb-core/chart/anchors.json` 的 `kinds`**（跟每日五圖共用，
  這裡讀它不抄它）。完整分工見 [`FILES.md`](FILES.md)。

## 第 1 步：載入現況

```
export BROKER_RESEARCH_ROOT=~/broker-research
python3 ~/kb-core/tools/research_verify.py
```

十四條檢查一次跑完。**FAIL 全部帶進報告**；`summary_length` 與
`one_engine` 出 WARN 不擋，但要說出是哪幾份。

沒有資料 repo 可看時 `chart_files_present` 與 `ledger_no_overdue`
回 **SKIPPED 不是 PASS** —— 那跟「檔案都在、都判完了」是兩件事。

接著看三個回執與 log：

```
cat ~/outbox/research/*.receipt.json | tail -20
tail -5 ~/outbox/research/publish.log
tail -5 ~/outbox/research/watch.log
```

**沒有回執代表 publish 根本沒跑**，那跟「回執說失敗」是兩件事。

## 第 2 步：認出問題屬於哪一層

| 症狀 | 在哪一層 | 先看 |
|---|---|---|
| 某份報告認不出券商／日期 | 第 1 層 入庫 | `extract.py`、`anchors.brokers` |
| 精華篇幅、原句、標籤、圖表 | 第 2 層 撰寫 | `preamble.md`、卷宗、`check_part.py` |
| 站台版面、原句牆 | 資料 repo 的 `index.html` | — |
| 發布回執非 0 | publish | `kb-core/tools/publish.py` 的七條設計 |
| 站台停在舊的一期 | 哨兵 | `checks/sentinel.py`、GitHub Actions |

**exit 11（不可改寫）在這一套有兩種意思**，要分開：

- **加了新報告** → 不會擋。`republish_rule` 是 `append_only`，
  回執 exit 0，log 印「改寫 …，系統的 `republish_rule` 判定這是允許的變更」。
- **已發布的某一份內容被改了或不見了** → 擋，回執指名是哪幾份。
  **不要改草稿去繞過它** —— 那條守衛擋的正是「已經給人看過的東西被悄悄換掉」。
  要撤稿由使用者 `git rm` 那一期重發，**那筆 revert commit 就是要有人看得見**。

## 第 3 步：動手之前

改**規格或門檻**走 [`MODIFY.md`](MODIFY.md)。
改**已發布的內容**先問過使用者 —— 見上面 exit 11 那一段。

## 第 4 步：回報

`research_verify` 的完整結果（PASS／WARN／FAIL／SKIPPED 各幾條，
FAIL 與 SKIPPED 逐條列出）、你改了哪幾個檔、**你判斷不了而跳過的東西**。

**回報你實際做到的，不是你打算做到的。**
