# 執行修改

第 4 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。**

## 改哪裡

| 要改的東西 | 動這個檔 | 連帶 |
|---|---|---|
| 規格細節（版面、章節、縱深寫法） | `HOUSEVIEW_BRIEF.md` 對應節 | 流程或分支跟著變才動 §7 prompt |
| 每月流程或分支 | brief **§7 啟動 prompt** | brief 對應規格節同一次改完 |
| 內容 JSON schema | **三處一組** | 見下方 |
| 渲染、版面、溢出判定 | `build_hv3.js` | `healthcheck_hv.py` 的對應檢查 |
| 每月盤點表、接入上游序列 | `prep_hv.py` | `FILES.md` 上游段落 |

規格與 §7 prompt 是一組：改一邊不改另一邊，就是在製造下一個漂移。

## 三處一組

動到 schema 時，這三處一起改，改完逐處回讀確認：

1. brief §8 schema
2. `build_hv3.js` 的 validateContent／NEED／RENDER
3. `healthcheck_hv.py` 的 payload 檢查

## 收尾

1. `CHANGELOG.md` 開一節，**五欄一個都不能少**：動到哪些檔／量測／怎麼驗的／怎麼倒回去／當時已知的風險。沒量過就寫「—」，不要內插。
2. 指標軌跡表加一列，brief 第 9 節版本行同步。
3. commit＋tag（前提：`git-init.sh` 已在 Mac 上跑過；還沒跑就先請使用者在 Mac 上跑，否則「怎麼倒回去」那一欄是空話）。
4. 回頭逐條確認 `FILES.md`「改動要保住的不變量」全部還在。

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步，不要往下走。

1. 兩期別 healthcheck 重跑（指令見 `MAIN.md` 第 1 步）：新期別沒有新的 FAIL，legacy 期別的計數與改動前相同。
2. `node ~/houseview/build_hv3.js content-YYYY-MM.json /tmp/test.pptx` 成功寫出檔案。
3. 跑 pptx skill 的 `validate.py`。
4. **轉 PDF 逐頁看圖**（`soffice.py --headless --convert-to pdf` → `pdftoppm -jpeg`），叫子代理逐頁檢查疊字、壓版、死白、圖表標籤重疊、版型重複、紅字密度失衡。版面與配色問題只有看圖抓得到——rainbow bug 與標籤相撞都是這樣抓到的。
5. 再叫一次子代理做第 2 步的漂移比對，確認這次改動沒有製造新的漂移。
