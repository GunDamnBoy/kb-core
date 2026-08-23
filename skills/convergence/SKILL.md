---
name: convergence-weekly
description: 產出主題匯流訊號報的每週一期。每週一台北 15:00 在 Mac mini 上執行；也可在互動對話說「跑這週的匯流」手動觸發。
---

# 主題匯流訊號報｜這一期怎麼做出來

**什麼算對的產出**在 `convergence-weekly/AGENT_BRIEF.md`（§0 定位與四種訊號、
§3 章節結構與 schema、§5 品質規則）。這份文件只寫流程，不重複規格；
**兩者衝突時以 `AGENT_BRIEF.md` 為準**，並在交付訊息中回報衝突。

排程開的是**全新對話、沒有任何記憶** —— 這份文件與 `AGENT_BRIEF.md` 就是全部的輸入。

**這份文件的正本在 `kb-core/skills/convergence/SKILL.md`。** 排程裡那一份是它的副本，
改動一律先改版控那份再整份貼過去。

- 網站 repo：https://github.com/GunDamnBoy/convergence-weekly
  （網址 https://gundamnboy.github.io/convergence-weekly/）
- 本機發布目錄：`/Users/macmini/convergence-weekly`

## 這一輪在哪裡跑（2026-08-23 改）

| 段 | 在哪 | 有什麼 | 沒有什麼 |
|---|---|---|---|
| 上游五庫 | 各自的 GitHub Actions（先跑完） | 網路、官方端點 | LLM |
| 備料與撰寫 | **這一輪（Mac 桌面版）** | LLM、檔案系統、網路 | 網路寫入 GitHub、git push |
| 發布 | Mac launchd（`publish.py`） | 網路、SSH 金鑰 | LLM |

**這一輪跑在 Mac 上，不是雲端。** 建立排程時要**夾帶資料夾**，
否則它會被當成雲端任務丟到容器裡跑 —— 而**雲端排程 session 拿不到本機檔案**：
`mcp__remote-devices__*` 整個命名空間不存在（2026-08-23 三次獨立測量），
於是草稿寫不出去、沒有回執、網站不更新，**而交付訊息看起來一切正常**。

這一輪與投顧（07:30）、每日五圖（11:30）**同一個形狀**：本機執行、`~/outbox` 直接寫檔。
2026-08-23 之前這一套是用 `device_commit_files` 過橋的雲端排程，那是錯的形狀。
**不要用 `SendUserFile`、不要找 `mcp__remote-devices__` 工具** —— 本機執行不需要橋。

**這一輪不推 GitHub。** 產出寫進 `~/outbox/convergence/`，
`com.kenny.kbpublish.convergence` 每分鐘掃一次、跑檢查當閘門、原子寫入、rebase、push、寫回執。

## 時間預算

**還沒有實測軌跡** —— 第一輪跑完把分段時間記進這一節。
（參考：投顧那一輪從 3 小時 45 分收斂到約 1 小時 35 分，最大的一塊是子代理。）

---

## 1. 備料（純程式，你不要自己讀任何原始 JSON）

```bash
rm -rf /tmp/cw-site-$(date +%F)
git clone --depth 1 https://github.com/GunDamnBoy/convergence-weekly.git /tmp/cw-site-$(date +%F)
python3 /tmp/cw-site-$(date +%F)/prepare.py \
    --work /Users/macmini/convergence-weekly/work \
    --site /tmp/cw-site-$(date +%F) \
    --emit-skeleton
```

**三件事各有理由，不要簡化掉：**

- **`--work` 一定要指到 `~/convergence-weekly/work`。** 那是 plist 裡
  `CONVERGENCE_WORK` 寫死的路徑，`publish.py` 的閘門要從那裡讀語料回查佐證。
  指到別處的樣子是：這一輪一切正常，回執回 BAD_INPUT。（`work/` 已 gitignore。）
- **clone 到 `/tmp` 而不是直接用 `~/convergence-weekly`。** 那個工作區歸
  `com.kenny.kbpublish.convergence` 所有，它每 60 秒在裡面 `pull --rebase`／`commit`／`push`。
  在別人的工作區裡跑東西，症狀會出現在**發布**那一邊，不是這一邊。
- **目錄名帶日期、而且先 `rm -rf`。** `/tmp` 的檔案會跨輪次殘留 ——
  2026-08-12 五圖那次事故就是 `/tmp/mk.py` 撞上前一輪的同名檔，
  `cat >` 因權限失敗但舊的那一份照樣被執行，把當期 JSON 覆寫成空殼，180 秒內上線。

**動手前先完整讀 `/tmp/cw-site-<今天>/AGENT_BRIEF.md`。**

`prepare.py` 會 clone 五庫、產五份摘要層（`adv`／`pod`／`bub`／`cotd`／`res`）、
`PREP.md`、`work/skeleton.json`、`work/stances.json`。

**`prepare` 回 exit 3 ＝ 五庫都沒有比上一期新的資料 → 依 §2.1 不產期。**
停在這裡，在交付訊息寫明「本次未產期」與各庫實際最新日期，**不寫任何檔案**。
這不是失敗，是設計。

**完成條件**：`work/PREP.md`、五份 `.txt`、`skeleton.json`、`stances.json` 都存在，
且 `prepare.py` 的退出碼被讀過。

## 2. 讀 `PREP.md` 與五份摘要層

**一次讀完，不要分段** —— 分段會產生多次快取寫入（×2 權重），是實測可見的成本。

**不要碰任何原始 JSON**，也**絕對不要把 `series` 與 `option` 讀進上下文**
（每日五圖單日 100KB 裡有 96KB 是那兩個欄位，零判讀價值）。

## 3. 兩個平行子代理萃取敘事側

**必須平行、必須互相看不到對方的檔案。** 這是正確性問題不是效率問題 ——
同一個上下文讀完兩庫會讓共振變成自我實現的預言。

- 子代理 A 讀 `work/adv.txt` → 8–14 個主題，每主題 3–5 條逐字佐證，
  另附「只出現一次但值得注意的訊號」5–8 條。
- 子代理 B 讀 `work/pod.txt` → 8–12 個主題，每主題 2–4 條逐字佐證，
  另附「podcast 已在講但新聞沒跟上的事」5–8 條。

**不要為 `cotd.txt` 或 `res.txt` 派子代理。**
每日五圖的選題與投顧同源，獨立萃取只會製造假共振的材料；
外資報告的 `crosscut` 本來就已經是綜合過的，再派一個只會複述它。
**量化側與賣方側由你自己讀** —— 裁判的證詞不應該經過另一個模型的轉述。

## 4. 主線合成（不可外包）

**先攤開量化側**（`PREP.md` 的量化底盤 ＋ 觸發器表 ＋ `cotd.txt` 的重製數字
＋ `res.txt` 的 `crosscut`），**再拿兩份敘事主題去對。**

**順序反過來做會找不到背離** —— 先讀敘事再看指標，你只找得到「指標支持敘事」
的部分。實測：第一次順序反了，只找到三條共振、一條背離都沒找到。
**先看裁判怎麼說，再聽雙方陳述。**

四個獨立聲音：**新聞側（投顧＋圖表合計一票）／節目側／量化側／賣方側**。
共振門檻仍是三方，理由見 `AGENT_BRIEF.md` §0。

這一步沒有機器把關，最容易提早收手。**完成條件**（逐項可勾）：

- [ ] 量化側的每一層變動都看過，且說得出「為什麼是這一層動」
- [ ] 兩份敘事主題都逐條對過量化側，**找過而沒有，跟沒找過，是兩件事**
- [ ] 上一期 `watch` 逐條驗收，結果寫進本期 `verdict`
- [ ] 賣方對帳做完（第 5 步）

## 5. 賣方對帳

`PREP.md` 的「賣方對帳」段列出當週到期的分析師主張。**逐筆處理，一筆都不能漏。**

寫進頂層 `rulings[]`：`{id, result, why}`。

- `result` 是 **應驗／部分應驗／落空／無法驗證／延後**（值域見 §3）。
- **每一筆都要寫 `why`。** 裁決沒有理由就不是裁決。
- 判不了就寫 `延後` 加理由 —— **到期而完全沒被碰的主張是安靜地掉的**。
- 「延後」不寫回帳本，那幾筆下一期照樣會被撈出來。那是刻意的。

同一批到期主張也要在 `verdicts` 節寫成人讀的版本（那一節是 `rulings[]` 的門面）。

## 6. 寫草稿

**以 `work/skeleton.json` 為底**寫到 `~/outbox/convergence/<本期日期>.draft.json`。

`quant` 整區已經抄好了，**直接沿用、不要重打** —— 那是機械抄寫，
手打既慢又會抄錯（第 002 期就是這樣把 `watch` 的 trigger id 標成 indicator id）。
記得填頂層 `schemaVer: "2"`。

**直接寫檔，不要過橋**（本機執行，沒有 `device_commit_files` 這回事）。
寫完用 `wc -c` 確認落地 —— **寫檔失敗與執行成功是兩件獨立的事。**

**不要直接寫 `data/`**，那是繞過閘門。

**完成條件**：`wc -c` 的位元組數與預期相符，且 JSON 可被 `json.load` 讀開。

## 7. 本機先驗一次，再等閘門

```bash
python3 /Users/macmini/kb-core/tools/convergence_verify.py \
    ~/outbox/convergence/<本期日期>.draft.json \
    --repo /Users/macmini/convergence-weekly \
    --work /Users/macmini/convergence-weekly/work
```

它跑的就是 `exit 10` 那一關的同一組檢查，**完全無副作用、不碰 git、不碰網路**，
十秒內回答。**一次退件的成本是一輪，一次本機驗證是十秒。**

**這一條與「不要自己先逐條回查一遍」不衝突，兩者講的是不同的事**：
不要做的是**用手**把每條佐證回查一遍（慢、而且手動那次還會漏掉 `list[]`）；
要做的是**讓程式跑一遍**。前者是重工，後者是省一輪。

**`SKIPPED` 不是 `PASS`。** 語料在 `work/` 底下，第 1 步做對了就不該出現 SKIPPED；
出現了代表 `--work` 指錯地方，回第 1 步。

**完成條件**：`convergence_verify.py` 回報 **0 FAIL**，且 SKIPPED 是 0。

## 8. 等回執

`com.kenny.kbpublish.convergence` 每分鐘掃一次，跑完會寫
`~/outbox/convergence/<本期日期>.receipt.json`。讀它的 `exit`：

| 退出碼 | 意思 | 這一輪要做的事 |
|---|---|---|
| 0 | 已發布 | 收工，把 commit 記進交付訊息，接第 9 步 |
| 10 | 內容沒過檢查 | 看 `detail` 指的是哪一條，改草稿重寫，回第 6 步 |
| 11 | 這一期的檔已存在且內容不同 | **不要改草稿** —— 已發布的一期就是已發布的樣子，掛 errata |
| 12 | 輸入或目的地壞掉 | 停下來回報，這不是內容問題 |
| 13 | 空輪次 | 草稿沒被看到 —— 檢查檔名與目錄層級（glob 非遞迴） |
| 14 | 網路或 SSH | 等下一輪自動重試；**它會自己完成**，不要重寫草稿 |
| 15 | rebase 衝突 | 停下來回報 —— 重跑不會好，有東西寫錯地方 |

**沒有回執**與**回執說失敗**是兩件不同的事：前者代表 `publish` 根本沒跑。

**完成條件**：手上有一份回執，且它的 `exit` 有被讀過並依上表處置。

## 9. 裁決寫回（回執 exit 0 之後才做）

```bash
python3 /Users/macmini/kb-core/tools/convergence_rulings_apply.py \
    /Users/macmini/convergence-weekly/data/<本期日期>.json
```

**先不加 `--apply` 跑一次看要改哪幾筆**，確認無誤再加 `--apply`。

它把終局裁決寫進 `broker-research-digest/data/stances.json` 的
`status`／`verdict`／`verdictDate`。外資報告下一輪重建會保留它們
（2026-08-23 實測 3/3 保留）。

## 10. 交付訊息（五行）

1. 本期最重要的判斷
2. 上一期 `watch` 的驗收結果
3. **本期裁決了幾筆賣方主張**（應驗／部分應驗／落空／無法驗證／延後各幾筆）
4. 帳本戰績（`calls` 的 N 勝 M 敗 K 未決）
5. 發現的資料缺口

附線上網址（**帶 cache-buster**），並確認期別按鈕數量與跨期趨勢的點數。
**末行寫發布狀態**：回執 exit 0 就寫「已上線」並附 commit。

---

## 這一輪不做的事

- **不要重述新聞。** 每一條都要有「因為幾個庫都／只有一庫講，所以⋯⋯」這層推論。
  **如果某一期讀起來像「本週新聞回顧」，那就是做失敗了。**
- **「本期判斷」必須表態。** 不要寫「值得持續觀察」—— 那是把判斷推給讀者。
- **單邊訊號只標記不判斷。**
- **不要為了湊滿章節而硬掰。** 某週真的沒有背離，就寫「本週五庫高度一致，
  這本身是訊號」。
- **不要重做券商之間的綜合** —— `crosscut` 已經做了，你把它當一票。
- **不要動 `index.html`**，除非 schema 真的變了。
- **不要跑本 repo 的 `verify.py`／`publish.py`／`cwlib.py`／`make_index.py`／
  `build_issue.py`／`healthcheck.py`** —— 它們 v2 全部退場，跑起來會出錯。
  這一套的閘門在 kb-core（`checks/convergence.py`），不在這個 repo 裡。
- **不要在 `~/convergence-weekly` 裡跑任何 git 指令。** 那是發布器的工作區，
  留下的 `index.lock` 會擋住它 —— 而那一次的症狀是**發布失敗**，不是這一輪失敗。
