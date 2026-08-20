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
3. ~~`scripts/chart/preamble.md`~~ —— 見下一則，那個指標本身是錯的形狀。

## 2026-08-20 深夜（續）｜雙軌決定、一個活著的 bug、以及一個我自己造的死連結

### 一、架構改判：兩軌都留，改用檢查抓漂移

稍早我把 `stored_option` 設成 false，前提是「只剩一個渲染器」。
使用者選了第三條路 —— **兩軌都留**（PNG 的排版規格不動、互動也不失去），
所以那個前提不成立，`stored_option` 改回 true，
`chart.no_stored_option` 換成 `chart.option_matches_spec`。

**這次改判要記下來的不是結論，是它推翻了什麼。**
我原本以為「兩軌從同一份 spec 渲染」就能解決漂移 —— 讀完 `chartkit.py` 才發現
那 891 行裡本來就是兩套實作（`render_static` 用 matplotlib、`echarts_option` 產 option），
**逐圖型各寫一次**。同一份 spec 只是讓它們從同一個地方開始各畫各的。

### 二、檢查的形式：不是比兩張圖，是問「option 有沒有忠實編碼 spec」

**實際發生過的漂移，錯的都在 option 那一側** —— 因為 PNG 每天有人看、網頁沒有。
所以靜態軌被當成參考實作，四條斷言全部從真實事故反推：

| 斷言 | 它當初藏住的方式 |
|---|---|
| 類別軸 `xAxis.data` 與序列長度對得上 | ECharts 按位置貼資料，錯位不報錯、整條位移 |
| waterfall 帶 `stackStrategy: "all"` | **漏掉時資料完全不變**，只有渲染行為變，每根從 0 往上長 |
| grouped／stacked 用 `barCategoryGap` 不用逐序列 `barWidth` | `barWidth` 是每一條不是一整組，兩條各 62% → 一組實佔 143% |
| `zero_line` 為真時 option 有 `markLine {yAxis: 0}` | 只有 PNG 有 |

第二條特別值得留意：**光比資料抓不到它**，必須直接斷言那個鍵。
因為 option 是存在日檔裡的，整組比對是純資料、不需要渲染，也因此能拿封存回測。

### 三、這條檢查一寫出來就抓到還活著的 bug

站上 **7 張標了 `zero_line` 的圖，只有 1 張的互動軌真的有零線** ——
而那 1 張是唯一的 timeseries。grouped_bar 4 張、scatter 1 張、waterfall 1 張全部沒有。

原因是 `_apply_zero_line` 那段程式**只寫在 timeseries 那條出口**，
而 `_echarts_new_kind` 與 scatter 早在前面就 `return` 了。
當初的測試案例剛好是 timeseries，所以**看起來修好了**——
舊規格自己記著的那句「**改一半比沒改更難發現**」就是這個。

在宣稱它是漂移之前先查過：那幾張的 option 裡沒有 markLine、沒有 markArea、
沒有 graphic、`yAxis` 也沒有任何零線設定 —— **沒有替代編碼**，零線只存在於 PNG。

修法是抽成共用函式讓三條出口都經過，讓「哪一種圖型」不再是變因。
`gauge` 與 `heatmap` 排除，條件與 `render_static()` 第 408 行逐字相同。

**驗收有三層**：

| 問題 | 答案 |
|---|---|
| 四種圖型都補上了嗎 | 1/7 → **7/7** |
| 原本對的那張有沒有被弄壞 | 沒有 |
| **有沒有順手改到別的東西** | 65 張圖重建 option，把零線 markLine 拿掉後**全部與原檔逐字相同** |

第三列才是「我只改了我以為我改的東西」的證據。歷史封存不回頭改寫，
所以站上那 6 張的互動軌維持原樣，而檢查在生產時只跑當日。

### 四、我替自己造了一個死連結

`SKILL.md` 裡寫著「取數眉角在 `scripts/chart/preamble.md`」，而那個檔案不存在。
更根本的是**那個形狀是錯的**：preamble 存在的理由是「採集 subagent 讀不到 brief」，
而 chart 是單一代理跑完五張圖 —— `subagent`／`子代理`／`派工` 在舊 brief 與
MAINTENANCE 裡**零命中**。我照抄 advisory 的骨架時沒問它適不適用。

改成 `chart/SOURCES.md`：一份**第 3 步才需要、靠指標到達**的參考檔，
不隨每次執行載入 —— 這樣 `BRIEF.md` 也留得住預算（實測 ~2,354 token，預算 4,000）。

順手寫了一段掃描，把 chart 這一套所有文件裡的相對路徑指標抓出來對存在性。
**它立刻抓到 `BRIEF.md` 裡還有第二處沒改** —— 我只修了 SKILL。
> **一個指標指向不存在的檔案，比沒有指標更糟**：它讓讀的人以為那份東西存在，
> 然後去別的地方找一個不存在的答案。

### 五、還沒做

1. **`tools/` 的去留** —— 架構定案是「兩軌都留」，所以 `chartkit.py` 不必重寫，
   問題只剩「它該住在資料 repo 還是 kb-core」。
   **這會動到每天 11:00 的關鍵路徑，建議明天那兩輪跑完再動。**
2. **`fetch.py`／`prefetch.py`** 同上。
3. 排程 plist 尚未安裝（`com.kenny.kbpublish.chart`），所以 chart 目前不會自動跑。

## 2026-08-20 收尾｜搬家的最後一哩、以及退休一個檢查腳本時差點掉的六條

### 一、`tools/` 清空了，殘骸留在 `_to_delete/`

`chart-of-the-day/tools/` 底下 16 個檔案全部移進 `tools/_to_delete/`（工具刪不了檔，
只能搬）。11 支 `.py` 逐檔比對過與 `kb-core/scripts/chart/` 的差異 ——
**全部只差在 repo 解析那一段**（舊制 `os.path.dirname(...)` 猜自己在資料 repo 底下，
新制走 `_repo.py` 明確傳入），沒有任何一支帶著沒搬過去的修正。

`dashpush-auto-push.sh`／`dashpush-repos.txt` 沒有新家 —— 推送改走
`publish.py` 的 outbox 草稿與回執，那條路會驗檢查、會留退出碼，
舊的背景推送兩者都沒有。

### 二、退休 `check_day.py` 之前，逐條比對它的每一個 `bad()`

**這一步差點被跳過。** 「它已經被 `checks/chart.py` 取代」是我自己寫在待辦清單上的
一句話，而那句話當時沒有任何證據 —— 12 條新檢查 vs 26KB 的舊腳本，
我沒有比對過就把它歸類成「superseded」。

實際比對 41 個 `bad()` 之後，**有六條在新檢查裡完全沒有對應的**：

| 補進去的檢查 | 它守的是什麼 | 沒有它會怎樣 |
|---|---|---|
| `chart.provenance` | 重製圖的 `inspired_by` 有 url、有原文日期、不在未來、七天內 | 重製的「題」變成沒有出處，而圖照樣畫得出來 |
| `chart.series_wellformed` | dates 與 values 等長、點數 ≥20、marker 只上有日期軸的圖型 | **類別軸寫了 marker 不報錯也不畫**，而 `reading` 會照著寫「已標在圖上」 |
| `chart.png_present` | 宣稱的 PNG 真的在磁碟上，且大於 20,000 位元組 | **空白圖不會拋例外** —— 檔案合法、只是上面沒有線 |
| `chart.prefetch_fresh` | 宣稱走 prefetch 時狀態檔在 30h 內，且序列不在失敗清單裡 | 用舊快取的那一輪**照樣會成功** |
| `chart.data_path_streak` | 連續走 browser 備援不超過 3 期 | 2026-08-06 起連九天「降級但成功」，沒有人把它當成故障 |
| `chart.release_day` | 發布日的當日主圖 slug 與 theme 對得上 | 這條規則一個月只觸發約三次，**漏掉不會有人發現** |

> **少掉的檢查不會報錯，只會全綠。** 一套檢查被另一套取代的時候，
> 「新的比較好」與「新的涵蓋了舊的」是兩個問題，而只有後者能讓舊的安全地死。

三條需要摸磁碟的（PNG 位元組、預抓狀態檔、近 14 期的 `data_path`）由
`systems/chart.py` 的 `build()` 取進 payload，檢查本身仍然不做 IO。
**取不到一律留 `None` 讓檢查判 SKIPPED** —— 給 0 或給空 dict 會讓
「沒量到」長得跟「量到了而且沒問題」一模一樣。

### 三、`prefetch_fresh` 的參照點：一條在回測裡永遠紅的檢查等於沒有

第一版拿 `now` 算快取年齡，於是回測 08-17 那天得到「已 59 小時未更新」——
**那是回測本身的產物，不是那天的事實**。改成用該輪的名目時刻
（日期＋`anchors.schedule.run`）當參照。

順著改出第二件事：狀態檔只有一份、會被後面的輪次覆寫，所以回測舊日期時
它常常**晚於**那一輪。那種情況答不出「當時新不新鮮」，回 SKIPPED 並說出原因 ——
判 PASS 等於拿一份根本不是那一輪用的快取替它背書。

回測驗收：08-17 全綠（17 PASS／1 SKIPPED），08-13 只剩那條已知的
`option_matches_spec`（歷史封存不回頭改寫）。檢查總數 61 → **67**，四套系統。

### 四、預抓終於有 plist 了

`kb-core/launchd/kbprefetch-chart.sh` ＋ `com.kenny.kbprefetch.chart.plist`（11:00）。
舊版住在資料 repo、假設 cwd 就是 repo；新版明寫 `CHART_REPO`，
**刻意不猜** —— 猜錯的樣子是「抓到了、寫進另一個目錄」，而那一輪看起來會是成功的。

查現況才發現這件事有多實在：`data/_prefetch_status.json` 停在
**2026-08-18T11:06，`host` 是 `MacBook-Pro.local`** —— 舊機器。
新的 Mac mini 從來沒跑過預抓，而在補上 `chart.prefetch_fresh` 之前，
**這件事不會出現在任何一條檢查裡**。

### 五、資料 repo 的四份舊文件掛了退場橫幅

`README.md`／`AGENT_BRIEF.md`／`MAINTENANCE.md` 頂上加了指向 kb-core 的對照表。
它們還沒刪，因為 `MAINTENANCE.md` 裡還有一些事故紀錄沒搬完 ——
但**照它做已經不行了**（那裡寫的 `python3 tools/check_day.py` 現在跑不動）。

### 六、還沒做

1. **chart 沒有每日執行者。** advisory 與 podcast 各有一個 Cowork 桌面排程，
   chart 還沒有 —— 也就是說 11:00 的預抓與每 60 秒的發布都就位了，
   **中間那一段沒有人跑**。
2. **chart 沒有任何看門狗。** 兩支 `kbwatch` 都不看它，發布鏈斷掉在 chart 這一套仍然是靜默的。
3. `MAINTENANCE.md` 的事故紀錄搬進 kb-core，然後那四份舊文件才能真的刪。

## 2026-08-20 深夜｜第一次真的按下預抓，它安靜了二十分鐘

裝好 `com.kenny.kbprefetch.chart` 之後手動驗證，終端機二十分鐘沒有任何輸出。
從快取目錄看得出來**一條 CSV 都沒被寫進去** —— `fetch.get()` 只在成功時寫檔，
失敗會拋例外、什麼都不留，所以「全部失敗」與「還在跑」在磁碟上長得一模一樣。

成因：**新的 Mac mini 上沒有 FRED 與 Tiingo 的金鑰。** 換機器時沒跟著走 ——
它們刻意不進版控，於是 `git clone` 拿不到、`git status` 也不會提。
沒有 key 就退到 `fredgraph.csv`，而 `SOURCES.md` 早就記著
**在這台機器上退路才是壞的那一條**（Errno 60），於是 46 條各自逾時 30 秒。

> 這是 `pmset` 那條教訓的第二個實例：**repo 裡看不到、換機器不會跟著走、
> 壞掉的樣子是「一切正常，只是沒有產出」。** 已寫進 `launchd/README.md`。

### 兩個都補進包裝腳本

**一、起飛前問金鑰。** 讀不到就 `exit 14`（ENVIRONMENT）中止。
刻意只問「讀不讀得到」而不打網路 —— key 錯的話 FRED 回 400 很快，
真正會拖死的只有「根本沒有 key」這一種。**這個問題要在兩秒內問完。**

**二、`--quiet` 改成看有沒有人在。** `[ -t 1 ]` 為真就逐條印，launchd 跑才只印摘要。

> **沉默同時符合「跑得好」與「全部失敗」。** 原本的寫法對 launchd 是對的
> （日誌不該每天多 46 行），對站在終端機前面的人卻是最壞的 ——
> 他唯一能做的判斷是「看起來像當掉了」，而那個判斷是錯的。
> 一個旗標服務誰，取決於誰在讀輸出，不是取決於誰在呼叫它。

台股那兩條（證交所、櫃買）免金鑰，所以這個病的典型樣子是
**美股與總經整片消失、台股正常** —— 記在 README 裡當辨識特徵。

### 補記：拿掉 `--quiet` 之後，它還是沉默的

金鑰補齊、預抓真的跑起來了（10 分鐘寫了 15 條快取），**而終端機依然一片空白。**

成因是同一行裡的第二個決定：輸出走 `| tee -a "$LOG"`，於是 python 的 stdout
從終端機變成管道，預設由行緩衝改成區塊緩衝，要積滿好幾 KB 才吐一次。
逐條進度確實印了，只是還在緩衝區裡。加 `PYTHONUNBUFFERED=1` 解決。

> **我加的是「讓它說話」，但同一行順手把它的嘴接到一個會囤積的管子上。**
> 修好之後的症狀與沒修一模一樣，所以第二次驗證時我差一點又去查網路。
>
> 這是本輪第三次撞到同一個形狀：**守衛／量測驗到的維度比它宣稱保護的低一層，
> 而失敗長得像正常輸出。** 前兩次是 docx 的 `written` 恆等於 `len(eps)`、
> 以及 `zero_line` 只修了 timeseries 那條出口。
> 這次的變體是：**可觀測性本身也需要被觀測。**

判斷「到底有沒有在跑」不要靠螢幕，靠磁碟：

```bash
find ~/chart-of-the-day/data/series -mmin -10 | wc -l
```

`fetch.get()` 只在成功時寫 CSV，所以這個數字同時回答了兩件事 ——
**還在跑嗎**，以及**抓到的比例對不對**。

### 補記二：我在它腳下換了地板

那一輪最後噴出 `line 54: ??launchd: command not found`，取數卻是完整的（34/46）。

成因是我自己：**在腳本正在執行的當下改了那個檔案。** bash 讀 script 是邊讀邊跑、
記著位元組位移的 —— 我在前段插了 4 行（約 200 位元組）修緩衝，
python 跑完、bash 回頭繼續讀時，舊位移已經指到別的地方，
於是它讀到某一行的中段（內容剛好含 `launchd`）並試著執行它。

> **在指令列上改一支正在跑的 shell script，等於在它腳下換地板。**
> 正確做法是改到暫存檔再 `mv` 過去 —— 原子改名讓還在跑的行程繼續用舊的 inode。
> 這跟「已發布的日檔不改寫」是同一條規則的不同面：
> **有東西正在讀它的時候，就不要原地改它。**

實質影響只有末三行沒跑到（結束時間那行日誌與退出碼）。**這次是良性的**，
但同樣的錯發生在 `publish.py` 或 `podcast_docx.py` 執行中就不是了。

### 基準對照

| | 2026-08-16（舊機） | 2026-08-20（Mac mini） |
|---|---|---|
| ok/requested | 34/46 | **34/46** |
| 失敗 | ^GSPC | ^GSPC（Yahoo 哨兵，設計如此） |
| 已知被擋、走替代品 | 11 | 11 |
| 耗時 | 8 分 53 秒 | 5 分 23 秒 |
| host | MacBook-Pro.local | Mac-mini.local |

搬機之後第一次全鏈路對上基準。**明天 11:00 的 launchd 輪次才是 `PYTHONUNBUFFERED`
與那三行末尾的真正驗收** —— 今晚這一輪跑的是修改前的版本。
