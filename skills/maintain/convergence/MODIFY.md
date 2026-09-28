# 執行修改

第 4 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。**

## 改哪裡

| 要改的東西 | 動這個檔 | 連帶 |
|---|---|---|
| 規格、判斷規則、單期 schema | `convergence-weekly/AGENT_BRIEF.md` | schema「一組一起改」（見下） |
| 流程或分支 | `kb-core/skills/convergence/SKILL.md` | 桌面排程同輪整份取代（見下） |
| 比對來源 | brief 第 0 節的表＋`prepare.py` 的 `REPOS` | 先問「它的上游是誰」（見下） |
| 發布、帳本、指紋、閘門 | kb-core `tools/publish.py`／`systems/convergence.py`／`checks/convergence.py` | kb-core 由 `push_kbcore` 自動推（要過語法與 selftest） |
| 為什麼這樣改 | `convergence-weekly/CHANGELOG.md`、`MAINTENANCE.md` 第 6 節 | 見「收尾」 |

## schema：一組一起改

動 schema 就是動一整組檔案，清單以 brief 第 3.0 節末為唯一正本——那份清單是活的，逐項照著走。

## 排程 prompt：整份取代、兩處同輪

`update_scheduled_task` 是**整份取代**：先讀現有全文，漏帶的段落等於刪除。改 `kb-core/skills/convergence/SKILL.md` 正本，**同一輪**把它的本文（frontmatter 以下）整份貼進 `update_scheduled_task`，兩者逐字一致。

## 新增比對來源

第一個要問的問題永遠是「**它的上游是誰**」。上游相同就是**同源**，同源要計為同一票，否則同一則新聞被數兩次（events 與圖表庫，這個坑踩過兩次）。第二個問題是「**這個 URL 是不是那個系統現役的 repo**」——系統 id 不等於 repo（投顧就是這樣連錯兩期）。

## 動到發布軌時的順序

- **`data/` 以外的檔一改，下一次發布就會 exit 15**，直到使用者手動提交。要透過發布軌推東西（例如掛 errata、推回補的帳本）時，**先發布、後改原始檔**。
- 要改 `data/calls.json`／`index.json` 這類衍生狀態：直接原子寫入本機檔，再用一次發布（例如最新一期原樣或加 errata 重交 outbox）把它們一起 commit＋push。發布前先在沙箱建一份 git repo＋bare remote 實跑 `publish.py`，確認回執再動正式 outbox。
- 帳本可以隨時從全部單期檔重算：`systems.convergence.fold_calls` 依日期逐期折入（改判會報錯，保留第一次裁決）。

## 收尾

`CHANGELOG.md` 每版四項全要：逐檔改動／被否決的選項／驗證方式／回溯要點；度量填 brief 與 prompt 的字元數（`len()`）。`MAINTENANCE.md` 第 6 節寫事故與決策。**交付訊息列出使用者要手動提交的檔案與確切指令。**

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步。

1. kb-core：`py_compile` 動到的檔，並跑 `import checks, systems; from kbcore import report; report.selftest()`，回 0 個問題。
2. 動到 `prepare.py` 時：在 `/tmp` 用新版實跑一次（`--work` 指容器本地），看 PREP 的涵蓋、帳本、🛑 與骨架形狀。
3. 動到 schema 或檢查時：對草稿實跑 `kb-core/tools/convergence_verify.py` 確認預期行為（對象是草稿，不是 `data/` 裡的歷史檔）。
4. **再叫一次子代理**獨立複查：這次改動有沒有製造新的漂移、瘦身時有沒有弄丟關鍵規則。
5. 線上帶 cache-buster 驗證，看期別按鈕數、跨期趨勢點數、記分板、errata 橫幅，而不只是最新日期。
6. 本檔或 `MAIN.md`、`FILES.md` 若因這次維護而過期：改 `~/kb-core/skills/maintain/convergence/` 正本，再把整個 `maintain` 目錄打包成 `.skill` 請使用者安裝（`save_skill` 只取代 `SKILL.md`，快取唯讀）。
