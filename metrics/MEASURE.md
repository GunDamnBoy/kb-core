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

## 怎麼跑：自動（2026-08-24 起的預設）

**輪次不跑量測，只寫一個 sidecar。** `com.kenny.kbusage` 每 600 秒掃一次 outbox，
撿到 sidecar 就跑這一支、把那一列 append 進 `metrics/usage.csv`、然後刪掉 sidecar。
腳本在 `launchd/kbusage.sh`。

### sidecar 的格式（**這是它唯一的家，run skill 不要抄**）

位置與那一套的**回執同一個目錄**：

```
~/outbox/<日期>.usage.json                  # advisory（回執在根目錄）
~/outbox/<系統 outbox 目錄>/<日期>.usage.json   # 其餘六套
```

四個欄位全部必填，缺一個 `kbusage` 會把它搬成 `.bad` 並記在日誌裡：

```json
{"system": "advisory",
 "date": "2026-08-24",
 "since": "2026-08-24T07:35:00+08:00",
 "transcript": "/Users/macmini/Library/Application Support/Claude/local-agent-mode-sessions/<a>/<b>/local_<c>/.claude/projects/<mangled>/<uuid>.jsonl"}
```

- `system`：下表第一欄的值域，打錯會被 `SYSTEMS` 擋下。
- `date`：`YYYY-MM-DD`，就是那一期的日期。它同時是**陳舊判定**的依據
  （超過 2 天還沒成功就搬成 `.failed`）—— 用它而不是檔案 mtime，
  因為 mtime 會被複製與備份重設，而「這是哪一天那一輪的」不會變。
- `since`：那一輪**開始**的時刻，ISO8601 帶位移。輪次自己記的第一個時刻就是它。
- `transcript`：**那一場自己的主逐字稿絕對路徑**，不是最新的那一份。

### 為什麼路徑由輪次寫，而不是腳本去找

`pick_transcript()` 預設挑 `CLAUDE_CONFIG_DIR/projects/*/*.jsonl` 裡**最新**的那一份。
在 Cowork 這個假設會錯，而且錯得很安靜：

- 每一場 Cowork 對話有**自己的** `local_<uuid>/.claude`，不是共用一個。
  「最新」是最近有人講話的那一場，不是那一輪排程跑的那一場。
- 排程輪次與事後的維護對話**會共用同一份逐字稿**（2026-08-24 實測：
  07:35 的 advisory 輪次與 09:47 起的維護對話在同一個 session）。
- **挑錯與挑對，算出來的數字都很合理** —— 只有檔名那一行看得出來。

輪次知道自己在哪一場（outputs 目錄的兄弟就是 `.claude`），所以由它寫。
`--transcript` 一旦給了，`pick_transcript()` 直接回傳它，
**既不挑也不做 90 分鐘的 staleness 判斷** —— Mac 睡著、launchd 延後、
那一場後來又有人講話，都不影響結果。

找法：`Glob` 樣式 `…/local_<uuid>/.claude/projects/*/*.jsonl`，
**取不在 `subagents/` 底下的那一個**（只有一個，其餘全是子代理；
`kbusage` 會自己從主逐字稿的路徑推出子代理目錄）。

### 上界不用 sidecar 給

`kbusage` 會自己用 `--until-receipt <date>` 去讀那一套的回執 `at`。
sidecar 可以選填 `until` 覆寫它，但**正常情況不要填** —— 回執的時刻是量測過的，
自己填的是自述。

---

## 怎麼跑：手動（自動那條沒動時的備援）

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
