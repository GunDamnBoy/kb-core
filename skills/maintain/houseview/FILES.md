# 檔案地圖、上游與 v3 體裁

第 1／2 步比對、排查版面問題、或動手改任何東西之前對照用。

| 檔案 | 角色 |
|---|---|
| `HOUSEVIEW_BRIEF.md` | 規格＋**第 7 節啟動 prompt**（兩者一組，改一邊就要改另一邊）；第 9 節版本行 |
| `build_hv3.js` | **現行產生器**。`node build_hv3.js content-YYYY-MM.json out.pptx`。validateContent 擋結構、DROPPED 擋版面溢出，兩者都中止不寫檔 |
| `build_hv.js` | **凍結的 legacy**（兩欄舊版面），只用於重建 2026-07 以前的期別 |
| `healthcheck_hv.py` | 唯讀健康檢查。`--content` 指定期別、`--quiet` 省輸出。**期別分流**：v3 規則只驗 ≥2026-08，legacy 不回溯變紅 |
| `prep_hv.py` | **每月開工先跑**：當月每日五圖約 4MB 壓成約 25KB 盤點表（軌道推薦、QA 狀態、上一期 verdict 對帳、立場表基準）。用盤點表取代整批讀 `data/*.json` |
| `market_data.py` | 九市場月線取數骨架。參數 `YYYY-MM` 必填，只在使用者的 Mac 上跑 |
| `CHANGELOG.md` | 每版五欄紀錄＋指標軌跡表（健康檢查基準看這裡）。維護時讀最新一兩節，每月執行不必讀 |
| `style-exemplar.md` | 縱深寫法的講稿原文範本（標竿：2026-08-10 鴻海講稿），校準「寫到什麼程度才算數」 |
| `git-init.sh` | 一次性 git 初始化，必須在 Mac 上跑 |

## 上游

- **`~/chart-of-the-day` 每日五圖**：一週七天、月約 150 張、11:30 產出。House View 是它登記的下游，PNG 頁尾自帶來源（所以 `image` 免填）。healthcheck 做跨 repo 配色漂移比對（ACCENT 是否仍為 #D70C18）。
- **`~/advisory-knowledge-hub` 投顧知識庫**（2026-08 起）：`metrics.py --pulse` 印五資產立場翻轉史（立場表可直接 diff「本月翻了幾次、何時翻、當時理由」）、`--tags` 印題材動能；thermo 風險溫度日序列與 `snap` 數值鏡像在其 `data/index.json` 各日 entry；每日 `watchReview` 是可引用的預測戰績。正本規格見該 repo brief §3.5。**`prep_hv.py` 尚未接入**，接入前屬手動取用；要接入就改 `prep_hv.py`，並在本檔與 CHANGELOG 各記一筆。

上游的資料或介面整個變了，轉去該系統的 `MAIN.md` 處理（每日五圖 → `chart/`、投顧知識庫 → `advisory/`），在本 repo 補是補假的。

## v3 體裁

1. **標題即判斷句**：「美國股市回顧」不合格，必須是可被反駁的一句話。
2. **散文正文為主**：核心章節每頁 2–4 段 prose，四段式「現象 → 機制 → 縱深 → 配置含義」。縱深是九個可逐頁檢查的手法＋全冊手法「三數字定錨」，**名單與規則的權威版本在 brief 第 1 節**（此處不重述），原文範本在 `style-exemplar.md`。條列只用於事實清單。
3. **圖表編號可指涉**：exhibit 渲染成「圖表 N｜caption」（每頁重新起算），散文用「（見圖表 N）」；`exsrc` 逐圖標來源、`image` 免填。
4. **每頁必有 lede**（標題下的導言列，紅豎線）。
5. **紅色只在四處**：eyebrow、句內 `**紅字**`、圖表主角、要點框邊條。品牌紅 **#D70C18** 統一 UI 與圖表（四角色配色制）。

章節組成：十五固定章＋焦點 1–2 頁＋條件式【驗收】章（上一期有 verdict 就必有）。**十五章清單以 brief §2 為準**——brief 與 §7 prompt 各存一份、第 2 步負責比對，此處不存第三份。

版面：**13.333×7.5 吋、三欄×兩列、微軟正黑體**。

## 改動要保住的不變量

healthcheck 逐項比對，第 4 步改完逐條確認還在：

- **版面常數**維持 13.333×7.5、三欄×兩列、微軟正黑體、#D70C18。
- **期別分流**：新規則 gate 在 ≥2026-08，已交付的期別不因規範升級事後不合格。
- **DROPPED 與 validateContent 全程開著**：寧可失敗不缺一句，失敗訊息會指出該縮哪頁。
- **查無就寫查無**：數字（含歷史年份）一律現查，查不到就寫「查無」或改定性敘述，錯的數字比缺的數字傷害大得多。權威版本在 brief §6 鐵律。
- **焦點議題挑固定章節以外的主題**。
- **`chartspec` 寫到同仁可直接操作**：`source` 例如「Bloomberg：SPX、S5INFT Index，PX_LAST 日頻」，`annotate` 含前例事件標註。
- **單序列長條圖一律設 `highlight`（或單色 colors）**，否則 FAIL：pptxgenjs 會逐點輪播調色盤，主角反而變灰（rainbow bug）。
