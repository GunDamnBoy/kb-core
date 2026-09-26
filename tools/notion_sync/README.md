# notion_sync — 五套系統 → Notion「產出庫」

每天把投顧知識庫、每日五圖、Podcast 摘譯、主題匯流訊號報、外資報告週摘的**每一期全文**
寫進 Notion「第二大腦 2.0 › 產出庫 Outputs」。沒有模型在裡面，不進 usage.csv。
它只讀各資料 repo 已發布的 `data/index.json` 與 `data/*.json`，**不碰任何一套系統的正本、副本或排程**。

## 怎麼跑
- GitHub Actions `notion-sync`：台北 12:45 與 23:45 各一次；手動 Run workflow 可選系統與筆數。
- 金鑰：repo secret `NOTION_TOKEN`（Notion 內部整合「kb-notion-sync」）。整合要被授權到「第二大腦 2.0」頁。
- 資料庫 id 寫在 `sync.py` 的 `DEFAULT_DB`；換資料庫就設環境變數 `NOTION_DB_ID`。

## 冪等與修復
- 每頁的「同步鍵」＝`<repo>/<檔名>@<sha1 前 8 碼>|v<排版版本>`。已存在且版本相同就跳過；**最新 10 期**會重算雜湊，內容變了就整頁換新。
- **改排版時把 `render.py` 的 `RENDER_VERSION` 改掉**：下一輪會把版本不同的頁（整段歷史）各重寫一次，之後回到只查最新 10 期。約 180 期、十分鐘左右。
- 寫入時先標 `PENDING:`，全部區塊寫完才改成正式鍵。中途失敗留下的 PENDING 頁，下一輪開頭自動丟垃圾桶重寫。
- 沒有同步鍵的頁（手動建的）永遠不碰。

## 退出碼
| 碼 | 意思 | 該做什麼 |
|---|---|---|
| 0 | 範圍內全部在 Notion | 無 |
| 1 | 有期數失敗，其餘照寫 | 看 log 裡的 `::error::` 行；下一輪會自動重試 |
| 2 | 設定／權限問題 | 金鑰沒設、過期，或整合沒被授權到頁面 |

## 上游改版時
每個 renderer 對不認得的欄位會用通用排版照印（`_leftover`），所以新增欄位不會靜默消失，
只是排版比較陽春。要調排版就改 `render.py` 對應系統的函式，然後跑離線驗收：

```
python sync.py --dry-run --cache <抓好的 JSON 目錄> --out /tmp/out
python check_render.py --out /tmp/out --cache <同一個目錄>   # 全文覆蓋率、API 限制、標籤
python test_sync_mock.py <同一個目錄>                        # 假 Notion API 端對端（冪等、中斷修復、改版替換、排版版本、429）
```
`--cache` 目錄的檔名格式是 `<repo>__data__<檔名>.json`（含 `index.json`）。

## 標籤
區域／主題用 `render.py` 的 `REGIONS`／`THEMES` 關鍵字對照，**只落在筆記用的那兩組固定清單**，不會新增選項。
