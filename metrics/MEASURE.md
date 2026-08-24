# 用量：量它，不要估它

**七套系統的收尾都做這一件事，而規則只有這一份。**
各套的 run skill 只放一行指向這裡 —— 這一段曾經被抄成三份
（advisory／chart／research 的 run prompt 各一份），
然後 `--until-receipt` 加進工具時三份都沒跟上，於是 broker 那一列
混進了一整場維護對話（43,339k／617 輪，高估數倍）。
**同一段話存在三個地方，就是三個會各自過期的地方。**

## 為什麼要量

代理**看不到自己的 usage 欄位**，只能估。
`scripts/podcast/metrics-columns.md` 對原本那四欄的來源寫得很誠實：
「人工，抄自當輪用量回顧」—— 那是自述。

> **自述與量測在 CSV 裡長得一模一樣，而只有一個能拿來做決定。**

## 怎麼跑

**在哪一台機器上跑，取決於逐字稿在哪一台機器上 —— 而那不是一個固定答案。**

| 執行環境 | 逐字稿在哪 | 怎麼跑 |
|---|---|---|
| Claude Code／雲端容器 | 容器裡的 `~/.claude/projects` | 直接跑，預設的 `CLAUDE_CONFIG_DIR` 就對 |
| **Cowork** | **Mac 上**的 `~/Library/Application Support/Claude/local-agent-mode-sessions/*/*/local_*/.claude` | **要在 Mac 的終端機跑**，並指定 `CLAUDE_CONFIG_DIR` |

Cowork 的版本：

```bash
BASE=$(ls -dt "$HOME/Library/Application Support/Claude/local-agent-mode-sessions"/*/*/local_*/.claude | head -1)
CLAUDE_CONFIG_DIR="$BASE" python3 ~/kb-core/tools/usage_report.py <系統id> --until-receipt <本輪日期>
```

`<系統id>` 是下表第一欄，`<本輪日期>` 是 `YYYY-MM-DD`。

**這一段在 2026-08-24 之前寫的是相反的**（「用 Bash（雲端容器）不是 device_bash，
逐字稿只存在於雲端那一側，在 Mac 上跑一定失敗」），而工具本身早在 08-23
就把訊息訂正過來了 —— **正本與工具講反，照正本做就一定量不到**。
2026-08-24 的 advisory 輪次就是這樣：照這份跑，工具直接回「找不到逐字稿」，
於是 `usage.csv` 到那一天為止**一列 advisory 都沒有**。

**Cowork 的沙箱那一側看不到 Mac 的逐字稿，也掛不上**（掛載會被明文拒絕），
所以在 Cowork 裡「跑不出來」是預期行為，不是這一輪沒花 token。
同理，那一段 `git clone kb-core` 也不需要：在 Mac 上跑就直接用 `~/kb-core`，
在雲端容器裡才需要先取一份。

## 切界線不是選配

**一個工作階段可能不只裝一件事。** 排程執行與事後的維護對話會共用同一份逐字稿：
2026-08-23 實測，整份掃完 30,744k，而日報那一輪其實是 6,611k —— **高估 4.6 倍**。

`--until-receipt` 拿 `~/outbox/<目錄>/<日期>.receipt.json` 的 `at` 當上界，
那是**那一輪真正落地的時刻**，比任何自述都可靠。

| 系統 id | outbox 目錄 | 怎麼切上界 |
|---|---|---|
| `advisory` | （根目錄，沒有子目錄） | `--until-receipt <日期>`，回執在 `~/outbox/<日期>.receipt.json` |
| `chart` | `chart` | `--until-receipt <日期>` |
| `podcast` | `podcast` | `--until-receipt <日期>` |
| `broker-research` | `research` | `--until-receipt <日期>`（**id 與目錄名不同**） |
| `bubble` | `bubble` | `--until-receipt <日期>` |
| `convergence` | `convergence` | `--until-receipt <日期>` |
| `houseview` | `houseview` | `--until-receipt <日期>` |

## 產出怎麼處理

它印出主線與各子代理的有效 token，以及**一行 CSV**。
把那一行原封不動 append 到 `~/kb-core/metrics/usage.csv`
（在哪跑就在哪 append —— Cowork 是 Mac 的終端機，雲端容器是容器裡）。

**不要自己估，也不要抄你以為的數字。**

## 對一眼再收工

它會把**挑到的逐字稿檔名與時間範圍**印出來。
**挑錯逐字稿與挑對的，算出來的數字都很合理** —— 差別只在那兩行看得出來。
輪次數與時間範圍對不上你這一輪的實際情況，就是挑錯了，重跑並指定 `--transcript`。

## 跑不出來的時候

回報「這一輪沒有量到用量」以及工具印的那一行原因，**不要填一個估的數字**。
少一列的 CSV 還是可信的；多一列估的就不是了。
