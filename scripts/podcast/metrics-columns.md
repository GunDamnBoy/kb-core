# `metrics.csv` 每一欄是什麼

**這是欄位定義的唯一的家。** 在此之前沒有這份文件，於是有四欄的定義只存在於
最早寫它們的那場對話裡 —— 2026-08-21 要補 08-20／08-21 兩列時就發現推不出來
（`brief_kb=55` 對不上 `BRIEF.md` 當時的 7.9 KB，差了七倍）。

> **用另一套定義填進同一欄，比留白更糟。** 留白看得出來是缺的；
> 填了看不出來是錯的，而那一欄的整條曲線從此不可比。

## 還在用的欄位

| 欄 | 定義 | 誰量 |
|---|---|---|
| `date` | 台北日期 | — |
| `episodes` | manifest 的集數 | healthcheck |
| `ok`／`degraded`／`failed` | 依 manifest 每集的 **`status`** 欄位分類（不是 `quality`） | healthcheck |
| `transcript_kb` | 當日 `~/podcast-transcripts/<date>/*.md` 的位元組總和 ÷ 1024 | healthcheck |
| `output_json_kb` | 已發布的 `data/<date>.json` 實際檔案大小 ÷ 1024 | healthcheck |
| `speaker_flags` | manifest 裡 `speakerNotes` 非空的集數 | healthcheck |
| `eff_tokens_k` | 當輪**加權**總 token ÷ 1000（重讀×0.1、寫入×2、產出×5） | **2026-08-22 起改由 `tools/usage_report.py` 讀逐字稿算**，寫進 `metrics/usage.csv` |
| `subagents` | 撰稿子代理數 | 同上 |
| `agent_turns` | 子代理來回次數總和 | 同上 |
| `subagent_tokens_k` | 子代理加權 token 合計 ÷ 1000 | 同上 |

> **這四欄原本的來源是「人工，抄自當輪用量回顧」—— 那是自述，不是量測。**
> 代理看不到自己的 usage 欄位，只能估。2026-08-22 換成讀逐字稿算，
> 四套系統共用一支腳本與一份 `metrics/usage.csv`（見 `metrics/README.md`）。
> 這裡這四欄保留給既有的歷史列，**新的一輪寫進 `usage.csv`，不再寫這裡** ——
> 同一個數字兩個家，遲早會有一天只對了一半。

> **⚠ podcast 這一套「排程自己那一側」寫不了，但 Mac 那一側寫得了（2026-08-23 實測）。**
> `usage_report.py` 要讀工作階段逐字稿，而 **Cowork 排程在沙箱裡跑，逐字稿不在這一側**：
> 沙箱沒有 `~/.claude/projects`（`exit 14`）；逐字稿確實在 Mac 的
> `local-agent-mode-sessions/<id>/.claude/projects/…`、目錄結構與腳本預期一致，
> 但 `request_cowork_directory` **明文拒絕掛載**（「Cowork's internal session storage…
> intentionally not accessible」）；`session_info__read_transcript` 只回訊息內容、不含 usage。
> 佐證：`usage.csv` 原本只有 `2026-08-22,broker-research` 一列——那是唯一跑在別種執行環境的系統。**08-23 補上了第二列 `2026-08-23,podcast`**，是在 Mac 上跑出來的。
> **⚠ 但這不等於「排程不留 transcript」**（那個結論 08-14 寫過、08-16 被推翻，別寫第三次）：
> 逐字稿**存在**，在 `~/Library/…/local-agent-mode-sessions/<帳號>/<工作區>/local_<階段>/.claude/projects/`，
> 08-23 用 `Glob` 實地看到。**搆不到的是排程那一側，不是這份資料。**
> `measure_session_tokens()` 裡那段死碼的 glob 樣式對得上（08-23 驗過），**但它整份掃完會高估數倍，不是拿掉 early-return 就好**——見 `MAINTENANCE.md` 第 6 節。
>
> **這四欄對 podcast 一律留空——量測值的家是 `usage.csv`，不是這裡。** 08-22 與 08-23 兩輪都因為排程副本
> 沒同步到那段指示，照舊版抄了自述值進來，於是 `eff_tokens_k` 出現
> 4913／235／276 三個相差 20 倍的值 —— **正是本檔開頭那句「用另一套定義填進同一欄，
> 比留白更糟」的實例，而且是發生在寫下那句話的同一份檔案所管的欄位上。**
> 08-23 那一列已抽掉，08-21／08-22 保留原樣（不改寫歷史，但它們不可比，別拿來畫曲線）。

**比效率看 `subagent_tokens_k ÷ transcript_kb`，不要用 `eff_tokens_k ÷ 集數`。**
後者混了固定開銷與當場的維護動作，除以集數得到的數字不可比（08-15、08-17 都踩過）。

## 退休的欄位（2026-08-21 宣布、**2026-08-23 程式才真的停填**）

`brief_kb`、`skill_kb`、`segments_done`、`podfetch_minutes`。

> **這四欄「宣布退休」與「真的不再產生新值」差了兩天。** 08-21 在本檔寫下「一律留空」，而 `healthcheck.py` 照樣天天填到 08-23 才被抓到——**退休的定義寫在這份文件裡、填值的程式在另一份，中間沒有任何人對帳**。所以 08-21／08-22／08-23 三列這幾欄都還有值，**那些不是「當時量到的東西」，是規則已經改了而程式沒跟上的產物**。

保留欄位是為了不改寫既有資料列 —— **舊值仍然是當時量到的東西**，
只是那個定義已經沒有人說得出來了，所以不再往下填。
前兩欄尤其失去意義：規格在 2026-08-20 搬進 `kb-core/podcast/`，
「brief 有多大」問的已經不是同一份檔案。

要復活其中任何一欄，先在這裡寫下定義與量法，再開始填 ——
**順序反過來就是這四欄當初的下場。**
