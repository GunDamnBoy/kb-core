# 每日五圖｜重建紀錄

## 2026-08-20 深夜｜第四套系統上底盤：輸出契約、12 條檢查、系統註冊

沿用既有的 `chart-of-the-day` 資料 repo，不開新的。

**決定性的理由是 House View 的 pptx 直接吃 `charts/<date>/*.png` 的路徑** ——
換 repo 等於弄壞一個不在重建範圍、也沒有人在顧的下游。
第二個理由是舊規格自己記著「新建的 repo 不會自動納入推送清單」，
那個坑踩過兩次（podcast 8/02、chart 8/05），開新 repo 是把同一類設定風險再進一次。

反方最強的論點是「並行比對三天」，但新底盤給了更好的做法：
`tools/chart_verify.py` 可以對任何一天跑完整檢查而**不產生任何副作用**，
不需要靠兩個 repo 換來。

### 一、架構決定：不存 option，兩軌從同一份 spec 渲染

舊制把 ECharts 的 `option` 存進日檔，於是同一張圖有兩份實作 ——
而舊文件反覆記載**雙軌漂移是這套系統最常見的缺陷類型**。最嚴重的一次是
瀑布圖在網頁上每根從 0 往上長（ECharts 預設 `stackStrategy: samesign`），
**圖上的結論與 `takeaway` 相反，卻不丟任何例外。**

實測 2026-08-17 那期：`option` 佔全檔 **43%**、`series` 佔 32%，兩者內容重複。

**兩種錯的代價不對稱**：雙軌漂移是正確性失效；
「舊圖用新版渲染器重畫會有樣式差異」只是版本問題，在 `about` 記 `renderer_version` 就能定位。

**但規則已定、機制未建。** 渲染器要能從 spec 畫出八種圖型才談得上不存 option，
所以 anchors 加了一個**具名的旗標** `rendering.renderer_ready: false`，
`chart.no_stored_option` 讀它、回 SKIPPED 並說出原因。
不把 `stored_option` 暫時改成 true 的理由：那會讓 anchors 說「我們存 option」、跟 BRIEF 矛盾，
而且未來看不出那是過渡狀態。**「還沒做」與「做過了沒問題」必須分得出來。**

### 二、盤點時我誤判了一次，而那正是要記進契約的東西

看到 18 張非折線圖的 `series` 是空的，一度結論「它們的資料只存在 option 裡，
所以『一年後能原樣重畫』只對 47/65 張成立」。**錯的。**

資料一直都在，只是**每種圖型有自己的欄位**：scatter 用 `pts`、heatmap 用 `cats`/`rows`/`matrix`、
長條用 `cats`/`groups`、waterfall 用 `cats`/`vals`、gauge 用 `gauge`。
**我只找了 `series`。**

那張對照表先前不在任何文件裡 —— 所以「series 是空的」看起來就像資料掉了。
現在它是 `anchors.kinds`，渲染層與檢查程式都照它走，
而 `chart.kind_data_present` 逐圖型驗，13 天 65 張圖全數 PASS。

### 三、`theme` 的值域不在 chart 這邊

`theme` 必須是投顧知識庫那十五個子類別之一 —— 它們是同一份東西。
舊系統把十五個字串硬寫進 `check_day.py` 的 `THEMES`，
2026-08-20 比對發現**兩邊逐字相同 —— 但那是運氣**：沒有任何機制在維持它。

所以 `systems/chart.py` 的 `build()` 把投顧的 anchors 一起讀進來，
`chart.theme_unique` 直接讀它的 `groups`。**投顧那邊改組名，這裡會立刻變紅。**

### 四、回測逼出一條錯的規格

12 條檢查拿 13 天封存跑過。第一輪 `chart.lengths` 有 6 天 FAIL，
**全部是 `standfirst`** —— 正是那個「規格寫著 60–100、`check_day.py` 從來沒驗過」的欄位。

量了才知道規格是錯的：

| 欄位 | 散文規格 | 實測 | 處置 |
|---|---|---|---|
| `headline` | 20–30 | 20–31、中位 27、P75 29 | 帶取 **20–32**（只有一天界外） |
| `standfirst` | 60–100 | 69–126、中位 98、P75 110 | 帶取 **60–130**（**6/13 天界外**） |

「規格與實作連續一週不一致而沒有人擋，代表那條規格從一開始就不可執行。」
而這一條連被違反都沒有被看見 ——
**一個沒有讀者的數字不會被違反，只會被無視**，然後在有人拿它當真的那天集體變紅。

`about.data_path` 同理：實測只有 8/15／16／17 三天有（值都是 `prefetch`），
那是預抓系統落地前後才加的欄位，所以 `known_exceptions.data_path_from = 2026-08-15`，
更早的日檔回 SKIPPED 而不是 FAIL。

### 五、回測結果

13 天 × 12 條：

```
              chart.*（依 id 排序）
  2026-08-05  ––!··✗······
  ...
  2026-08-17  ·····✗······
```

**11 條在 13 天全數 PASS 或 SKIPPED**；唯一全紅的是 `no_stored_option`，
那是設計如此（舊制存了 option，歷史不改寫）。
`footer_lines` 兩筆 WARN 剛好落在 3 行的邊界上，是真的。

自檢也抓到我一個錯：`footer_lines` 的 `near_miss` 我設成 9 行而內容是 10 行，
於是「剛好還在合格側」的樣本也被觸發了。**`fixture` 證明檢查會叫，
`near_miss` 證明它在對的地方叫** —— 這次是後者救的。

### 六、今晚做到哪裡

| 已完成 | 檔案 |
|---|---|
| 輸出契約 | `chart/anchors.json`（24 區塊）、`chart/BRIEF.md` |
| 檢查 | `checks/chart.py`（12 條，全庫 61 條） |
| 系統註冊 | `systems/chart.py`（第四套） |
| 每日步驟 | `skills/chart/SKILL.md` |
| 無副作用的驗證入口 | `tools/chart_verify.py` |
| 資料 repo 接線 | `.kb-data-repo`、`deploy.yml` 加上線驗證、`sentinel.yml` |
| 排程 | `launchd/com.kenny.kbpublish.chart.plist`、`env.py` 登記 |

**還沒做（下一刀）**：

1. **渲染器** —— 兩軌從 spec 畫出八種圖型。這是 `renderer_ready` 翻成 true 的前提，
   也是今晚唯一沒動的大塊。
2. **取數層** —— `fetch.py`／`build_series.py`／`prefetch.py` 還在資料 repo 的 `tools/` 裡。
   **今晚刻意不動它們**：那是目前唯一能產出一天的東西，移掉等於讓管線完全不能跑。
3. `scripts/chart/preamble.md` —— SKILL 指到它，檔案還不存在。
