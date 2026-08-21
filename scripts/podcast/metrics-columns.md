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
| `eff_tokens_k` | 當輪**加權**總 token ÷ 1000（重讀×0.1、寫入×2、產出×5） | 人工，抄自當輪用量回顧 |
| `subagents` | 撰稿子代理數 | 同上 |
| `agent_turns` | 子代理來回次數總和 | 同上 |
| `subagent_tokens_k` | 子代理加權 token 合計 ÷ 1000 | 同上 |

**比效率看 `subagent_tokens_k ÷ transcript_kb`，不要用 `eff_tokens_k ÷ 集數`。**
後者混了固定開銷與當場的維護動作，除以集數得到的數字不可比（08-15、08-17 都踩過）。

## 退休的欄位（2026-08-21 起一律留空）

`brief_kb`、`skill_kb`、`segments_done`、`podfetch_minutes`。

保留欄位是為了不改寫既有資料列 —— **舊值仍然是當時量到的東西**，
只是那個定義已經沒有人說得出來了，所以不再往下填。
前兩欄尤其失去意義：規格在 2026-08-20 搬進 `kb-core/podcast/`，
「brief 有多大」問的已經不是同一份檔案。

要復活其中任何一欄，先在這裡寫下定義與量法，再開始填 ——
**順序反過來就是這四欄當初的下場。**
