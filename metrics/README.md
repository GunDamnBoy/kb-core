# 四套系統的用量帳

`usage.csv` 一輪一列，**由 `tools/usage_report.py` 讀逐字稿算出來，不是抄回報的**。

## 為什麼不沿用 podcast 原本那四欄

`scripts/podcast/metrics-columns.md` 對來源寫得很誠實：**「人工，抄自當輪用量回顧」**。
那是自述——代理回報它**認為**自己用了多少，然後有人抄進 CSV。
而代理看不到自己的 usage 欄位，只能估。

> **自述與量測在 CSV 裡長得一模一樣，而只有一個能拿來做決定。**

**這份 CSV 只收量測出來的列。** podcast 2026-08-22 之前那幾輪的數字是自述的，
留在 `scripts/podcast/metrics.csv`，**不要搬過來** ——
搬過來之後就再也分不出哪幾列可以信。

## 有效 token 的權重只有一個家

重讀 ×0.1、寫入 ×2、產出 ×5、新輸入 ×1 —— 寫在 `usage_report.py` 的 `W`。
四套共用，不然「這輪比上輪貴」會變成「兩邊用了不同的尺」。

## 怎麼比

**比效率看 `subagent_tokens_k ÷ 工作量`**（podcast 用逐字稿 KB、research 用份數），
不要用 `eff_tokens_k ÷ 件數` —— 後者混了固定開銷與當場的維護動作。
這一條是 podcast 2026-08-15／08-17 兩次踩出來的，逐字適用於其他三套。

## 欄位

| 欄 | 意思 |
|---|---|
| `date` | 逐字稿最後一筆的日期 |
| `system` | `advisory`／`chart`／`podcast`／`broker-research` |
| `eff_tokens_k` | 主線＋子代理的加權合計 ÷ 1000 |
| `main_turns` | 主線帶用量的輪次 |
| `subagents`／`agent_turns` | 子代理個數與來回總和 |
| `subagent_tokens_k` | 子代理加權合計 ÷ 1000 |
| `out_tokens_k`／`cache_read_k`／`cache_write_k` | 未加權的原始數，用來看結構往哪偏 |
| `transcript` | 量的是哪一份 —— **挑錯逐字稿與挑對的，數字都很合理** |
