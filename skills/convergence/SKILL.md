---
name: convergence-weekly
description: 產出主題匯流訊號報的每週一期。每週一台北 15:00 在 Mac mini 上執行（桌面排程 convergence-weekly-1500）；也可在互動對話說「跑這週的匯流」手動觸發。
---

產出「主題匯流訊號報」的本期一期。全程繁體中文（台灣用語）。

**什麼算對的產出**在 `convergence-weekly/AGENT_BRIEF.md`（§0 定位與四種訊號、§3 章節結構與 schema、§5 品質規則）。這份 prompt 只寫流程與環境事實，不重複規格；**兩者衝突時以 `AGENT_BRIEF.md` 為準**，並在交付訊息回報衝突。

排程開的是全新對話、沒有任何記憶——這份 prompt 與 `AGENT_BRIEF.md` 就是全部的輸入。**這份 prompt 的正本在 `kb-core/skills/convergence/SKILL.md`**，排程裡這一份是整份貼過來的副本（v2.1，2026-09-29）。

- 網站 repo：https://github.com/GunDamnBoy/convergence-weekly（https://gundamnboy.github.io/convergence-weekly/）
- 本機發布目錄：`/Users/macmini/convergence-weekly`

## 第 0 步：環境自檢（**沒過就停，不要往下做**）

這一輪跑在 Linux 容器裡，只有被夾帶的資料夾看得到。應該有四個：
`convergence-weekly`、`outbox`、`kb-core`、`broker-research-digest`。

bash 的掛載點是 `/sessions/<session>/mnt/<資料夾>`，**session 名每輪都不同，用 `ls -d /sessions/*/mnt/*/` 找出實際路徑，不要寫死**。Read/Write/Edit 則用 `/Users/macmini/...` 這種主機路徑。

逐項確認，任何一項失敗就**立刻停下來、不要產草稿**，在交付訊息第一行寫「環境自檢失敗：<哪一項>」：

- [ ] `<mnt>/convergence-weekly/data/index.json` 讀得到
- [ ] `<mnt>/outbox/convergence/` 存在且可寫：**覆寫固定檔名** `<mnt>/outbox/convergence/.cw-probe`（`date > …`）再讀回來。**不要每輪換檔名、也不要嘗試刪它**——這個掛載點不允許刪檔，刪不掉不是失敗，換檔名只會讓 outbox 越積越多
- [ ] `<mnt>/kb-core/tools/convergence_verify.py` 讀得到
- [ ] `<mnt>/broker-research-digest/data/stances.json` 讀得到

**2026-08-24 那一輪就是敗在這裡**：只夾帶了 `convergence-weekly`，所以前面九步全部正常、只有最後一哩是空的，而交付訊息看起來一切正常。**這一步存在的唯一理由，是把安靜的失敗換成大聲的失敗。**

## 1. 備料（純程式，不要自己讀任何原始 JSON）

```bash
SCRATCH=/tmp/cw-$(date +%F)-$RANDOM$$        # 帶日期「與亂數」——見下方
rm -rf $SCRATCH && mkdir -p $SCRATCH/site $SCRATCH/work || exit 9
git config --global --add safe.directory '*'
git clone --depth 1 https://github.com/GunDamnBoy/convergence-weekly.git $SCRATCH/site
grep -q 'GunDamnBoy/advisory-rewrite"' $SCRATCH/site/prepare.py || echo "SOURCE_CHECK_FAILED"
python3 $SCRATCH/site/prepare.py --work $SCRATCH/work --site $SCRATCH/site --emit-skeleton
```

**四件事各有理由：**

- **`grep` 印出 `SOURCE_CHECK_FAILED` 就停**，交付訊息第一行寫「環境自檢失敗：clone 下來的 prepare.py 仍指向舊投顧 repo——convergence-weekly 的 v2.1 修正尚未推上 GitHub」。投顧的**系統 id** 是 `advisory-knowledge-hub`，**repo** 是 `advisory-rewrite`；同名舊 repo 8/18 起停更、clone 照樣成功，第 008、009 期就是這樣把「抓錯 repo」寫成「投顧庫窗口內無檔」。
- **`--work` 要指到容器本地的 `$SCRATCH/work`，不能直接指到掛載進來的 `convergence-weekly/work`。** 掛載檔案系統不支援 git 的 lock 語意（`unlink .git/config.lock: Operation not permitted`），`prepare.py` 的 clone 會當場失敗。**跑完之後再把產物複製過去**（見第 1b 步）。
- **目錄名要帶日期「與亂數」。** `/tmp` 會跨輪次殘留，而且殘留檔可能是別的 uid 擁有、`rm -rf` 刪不掉又不報錯——2026-08-24 那輪就撿到前一天的 `PREP.md` 與五份 `.txt`（沒有 `skeleton.json`），差點拿舊資料寫本期。**做完備料要檢查檔案的 mtime 是今天。**
- **`prepare` 回 exit 3 ＝ 五庫都沒有比上一期新的資料 → 依 §2.1 不產期。** 停在這裡，交付訊息寫明「本次未產期」與各庫實際最新日期，**不寫任何檔案**。這不是失敗，是設計。

**動手前先完整讀 `$SCRATCH/site/AGENT_BRIEF.md`。**（Read 工具讀不到 `/tmp`，先 `cp` 到 outputs 再讀。）

### 1b. 把語料複製進發布器讀得到的地方

閘門會從 `CONVERGENCE_WORK`（`/Users/macmini/convergence-weekly/work`，plist 寫死）讀語料回查佐證。**缺了語料，每一條逐字比對都會 vacuously 通過，回執回 BAD_INPUT。**

```bash
cp $SCRATCH/work/{PREP.md,skeleton.json,stances.json,adv.txt,pod.txt,bub.txt,cotd.txt,res.txt} <mnt>/convergence-weekly/work/
mkdir -p <mnt>/convergence-weekly/work/bub && cp $SCRATCH/work/bub/data.json <mnt>/convergence-weekly/work/bub/
```

（`work/` 已 gitignore。**不要在 `/Users/macmini/convergence-weekly` 裡跑任何 git 指令**——那是發布器的工作區，留下的 `index.lock` 會擋住它，而症狀會出現在發布那一邊。）

## 2. 讀 `PREP.md` 與摘要層

**一次讀完，不要分段**（分段會產生多次快取寫入，×2 權重）。**不要碰任何原始 JSON**，尤其**絕不要把 `series` 與 `option` 讀進上下文**。

## 3. 兩個平行子代理萃取敘事側

**必須平行、必須互相看不到對方的檔案**——同一個上下文讀完兩庫會讓共振變成自我實現的預言。

- 子代理 A 讀 `adv.txt` → 8–14 個主題，每主題 3–5 條逐字佐證，另附「只出現一次但值得注意的訊號」5–8 條。
- 子代理 B 讀 `pod.txt` → 8–12 個主題，每主題 2–4 條逐字佐證，另附「podcast 已在講但新聞沒跟上的事」5–8 條。

兩者都要求：**佐證逐字，寧可少寫也不要編**；一次把整份檔案讀完；**只准讀自己那一份**（告訴它檔案路徑，並明令不准讀同目錄其他檔）。`adv.txt` 為 0 位元組時不派 A，並在 `gaps` 與 `about.run` 寫明。

**不要為 `cotd.txt` 或 `res.txt` 派子代理**——五圖選題與投顧同源，外資的 `crosscut` 本來就已綜合過。**量化側與賣方側由你自己讀**，裁判的證詞不該經過另一個模型轉述。

## 4. 主線合成（不可外包）

**先攤開量化側**（`PREP.md` 量化底盤 ＋ 觸發器表 ＋ `cotd.txt` 重製數字 ＋ `res.txt` 的 `crosscut`），**再拿兩份敘事主題去對。順序反過來會找不到背離。**

四個獨立聲音：新聞側（投顧＋圖表合計一票）／節目側／量化側／賣方側。共振門檻三方。

**量化佐證只能取自 `indicators`／`dims`／`stage`／`tw`（與觸發器），絕對不能取自 `events`。** `events` 是 Google News，與投顧同源——拿它當量化證據，同一則新聞會被數兩次、共振是假的。它只能拿來核對投顧側漏了什麼（哨兵用途）。

完成條件（逐項可勾）：量化側每一層變動都說得出為什麼；兩份敘事主題都逐條對過量化側；**上一期 `watch` 逐條驗收、結果寫進本期 `verdict`**；**PREP 訊號帳本段列出的每一筆未結案帳目都看過，能裁決的在 `calls.close` 結案**；賣方對帳做完。

## 5. 賣方對帳

`PREP.md` 的「賣方對帳」段列出當週到期的分析師主張。**逐筆處理，一筆都不能漏。** 寫進頂層 `rulings[]`：`{id, result, why}`，`result` ∈ 應驗／部分應驗／落空／無法驗證／延後。**每一筆都要寫 `why`。** 判不了寫「延後」加理由——**到期而完全沒被碰的是安靜地掉的**。同一批也要在 `verdicts` 節寫成人讀版本。本期 0 筆到期時，那一節仍要寫一個說明 item（每節至少一個 item）。

## 6. 寫草稿

**以 `$SCRATCH/work/skeleton.json` 為底**，`quant` 整區已抄好，**直接沿用不要重打**。骨架已是 v2 形狀（`schemaVer:"2"`、六節 `resonance → divergence → verdicts → taiwan → charts → single`、五列 `coverage`、空的 `rulings[]`），只填標「（填：…）」的欄位與 items。

**`calls`**：新判斷用 `calls.open` 登帳（只登可證偽的，id 用 `c<期號>-<序號>`），能裁決的舊帳用 `calls.close`（`hit`／`miss`／`expired`）。帳本由發布器機械折入：**已結案的帳目不得改判**（會 exit 10）；同一個 result 再結一次是 no-op。PREP 列出來的都是真的未結案——不要重結已結的。

**三個會讓閘門 FAIL 的細節（實測）：**

- **`<code>` 的抓取正則是 `<code>([a-z0-9_]+)</code>`，只吃小寫。** 寫 `l1`／`l2`／`l3`／`twheat`，不要寫 `L1`／`twHeat`；`trigLit`、`qa_flags`、`rulings[]` 不是欄位名，**不要包 `<code>`**。
- **`list[].body` 與 `evidence[].t` 會被「全片段」逐字回查**，所以它們必須是**純原句**，自己的分析要放到 `body[]`／`cols[]`／`call.body`（那幾欄不回查）。
- `evidence[].d` 一律 `M/D`；`evidence[].s` 只能是 監控／投顧／節目／圖表／**券商**；同一段佐證不得跨 item 重複。

草稿寫到 `/Users/macmini/outbox/convergence/<本期日期>.draft.json`。**不要直接寫 `data/`**（繞過閘門）。**先在別處組好、本機驗過再寫進 outbox**——outbox 裡的草稿一分鐘內就會被發布，而且刪不掉。寫完用 `wc -c` 確認落地、且 `json.load` 讀得開——**寫檔失敗與執行成功是兩件獨立的事。**

## 7. 本機先驗一次，再寫進 outbox

```bash
python3 <mnt>/kb-core/tools/convergence_verify.py <草稿路徑（outbox 以外）> \
    --repo <mnt>/convergence-weekly --work <mnt>/convergence-weekly/work
```

跟 `exit 10` 那一關同一組檢查，**無副作用、不碰 git、不碰網路**，十秒內回答。**一次退件的成本是一輪，一次本機驗證是十秒。**

完成條件：**0 FAIL**，且 SKIPPED 只有 `index_snapshot` 一條（發布前索引裡本來就還沒有本期，這條必然 SKIPPED）。**其他任何 SKIPPED 代表第 1b 步的語料沒到位，回第 1b 步——SKIPPED 不是 PASS。** 帳本折入不在這支的檢查範圍內，錯了會在回執出現（exit 10 @ side-files）。

## 8. 等回執

`com.kenny.kbpublish.convergence` 每分鐘掃一次，寫 `~/outbox/convergence/<日期>.receipt.json`。讀它的 `exit`：

| 退出碼 | 意思 | 要做的事 |
|---|---|---|
| 0 | 已發布 | 收工，commit 記進交付訊息，接第 9 步 |
| 10 | 內容沒過閘門，或帳本折不進去（`stage` 為 `side-files`） | 看 `detail`，改草稿重寫，回第 6 步 |
| 11 | 該期檔已存在且內容不同 | **不要改草稿**，掛 errata（見 brief §4 末） |
| 12 | 輸入或目的地壞掉 | 停下來回報 |
| 13 | 空輪次 | 草稿沒被看到——檢查檔名與目錄層級（glob 非遞迴）|
| 14 | 網路或 git | **它會自己重試完成**，不要重寫草稿 |
| 15 | rebase 衝突，或 repo 有 `data/` 以外沒提交的變更（`stage` 為 `worktree-dirty`） | 停下來回報（通常是維護改了原始檔沒提交），重跑不會好 |

**沒有回執**與**回執說失敗**是兩件不同的事：前者代表 publish 根本沒跑。完成條件：手上有一份回執，且 `exit` 被讀過並依上表處置。

## 9. 裁決寫回（回執 exit 0 之後才做）

```bash
python3 <mnt>/kb-core/tools/convergence_rulings_apply.py \
    <mnt>/convergence-weekly/data/<本期日期>.json \
    --stances <mnt>/broker-research-digest/data/stances.json
```

**先不加 `--apply` 跑一次看要改哪幾筆**，確認無誤再加 `--apply`。「延後」不寫回。`rulings[]` 為空時它是 no-op，照樣要跑一次留紀錄。

## 10. 交付訊息（五行）

1. 本期最重要的判斷
2. 上一期 `watch` 的驗收結果
3. 本期裁決了幾筆賣方主張（各結果幾筆）
4. 帳本戰績（**讀發布後的 `<mnt>/convergence-weekly/data/calls.json`**：N 勝 M 敗 K 未決，本期結了哪幾筆）
5. 發現的資料缺口

附線上網址（**帶 cache-buster**），確認期別按鈕數量與跨期趨勢點數。**末行寫發布狀態**：exit 0 就寫「已上線」並附 commit。

## 用量

不必做事：`com.kenny.kbscan` 每天從逐字稿自動量（系統 id `convergence`）。規則的唯一正本在 `kb-core/metrics/MEASURE.md`，這裡不抄。

## 這一輪不做的事

- **不要重述新聞。** 每一條都要有「因為幾個庫都／只有一庫講，所以⋯⋯」這層推論。**讀起來像「本週新聞回顧」就是做失敗了。**
- **「本期判斷」必須表態**，不要寫「值得持續觀察」。
- **單邊訊號只標記不判斷。**
- **不要為了湊滿章節而硬掰**——真的沒有背離就寫「本週五庫高度一致，這本身是訊號」。
- **不要重做券商之間的綜合**（`crosscut` 已經做了，當一票）。
- **不要動 `index.html`**，除非 schema 真的變了。
- **不要跑本 repo 的 `verify.py`／`publish.py`／`make_index.py`／`build_issue.py`／`healthcheck.py`**——v2 全部退場，跑起來會出錯。閘門在 kb-core 的 `checks/convergence.py`。（`cwlib.py` 是 `prepare.py` 的函式庫，不是要你直接跑的東西。）
- **不要在 `/Users/macmini/convergence-weekly` 裡跑任何 git 指令，也不要改那裡 `data/` 以外的檔**（改了沒提交，publish 會回 exit 15）。
