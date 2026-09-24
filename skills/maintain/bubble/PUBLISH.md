# 交付、線上驗證與「網站沒更新」排查

本工作階段對 repo 只讀不寫，所以發布一律走這裡。權威流程是 `MAINTENANCE.md` §3。

## 交付三個檔

- 一般改動：commit 到 /tmp 的 clone（身分 GunDamnBoy）→ `git format-patch -1 --stdout` → SendUserFile，由使用者 `git am` 後推送。
- 只改 `data.json`：交 `data-YYYY-MM-DD.json`，走 `bubble-publish`。
- 兩種情況都要連同**內嵌新資料的離線 HTML**（history 裁 60 筆）一起交付。`AGENT_BRIEF.md` 的交付節明定三個交付檔；漏了離線 HTML，fetch 失敗時使用者看到的就是舊資料。

檔名格式要對得上 `bubble-publish` 的 glob，commit 訊息照 brief 的格式。全程不嘗試 push、不索取或使用 token。

## 線上驗證（等使用者說推完了再做）

**用 `WebFetch`，不用 `curl`。** 本容器的 Bash 連不到 `gundamnboy.github.io`（回 http=000，不是逾時也不是 404，是連線直接被擋），curl 會拿到空字串、接在後面的 `python3 -c` 丟 JSONDecodeError，而流程往下走看起來像沒事。等 60–90 秒再抓：

```
WebFetch url: https://gundamnboy.github.io/ai-bubble-monitor/data.json
prompt: Report verbatim the value of meta.built, the top-level composite number, and quadrant.regime. Output only those three values.
```

比對 `meta.built` 與 `composite` 是不是剛推的那一版。**只看網頁上的日期不夠**——Pages 沒重建時日期也會是舊的，而那正是最需要抓到的情況。

**拿到舊值時**：這個 URL 有 15 分鐘快取，唯一經實測有效的 cache-buster 是**換檔名**——抓這次推送裡改過的另一個檔案（`README.md`、`MAINTENANCE.md`…），它若是新版，站台就已經好了、`data.json` 只是快取。乾淨 URL 是耗材，一個檔名只能用一次；全部用完還不確定就等 15 分鐘，或直接看 repo 的 commit。（`?t=` 與多打斜線都無效：快取鍵忽略 query string、路徑會被正規化。）

## 「網站沒更新」的排查順序

先定位斷在哪一層，再決定要不要動程式：

1. `data.json` 在 repo 裡也是舊的 → Actions 沒跑或整批失敗，去看 Actions log。
2. repo 裡是新的、網站是舊的 → **Pages 沒重建**，先確認 workflow 最後的 `POST /pages/builds` 步驟還在且沒失敗。
3. 兩邊都新、只有瀏覽器是舊的 → 快取。**硬重新整理（Cmd/Ctrl+Shift+R）**；`?v=時間戳` 一般也有效，但未經實測、當成試試看而不是保證。WebFetch／Pages 邊緣那層快取對 query string 確定無效，改用上一節的換檔名。

## 閘門在你動手前就可能是紅的：偶發的來源失敗

`auto_publish.py` 以 `gate.py` 與 `healthcheck.py` 當閘門，任一不過就 `park` 並 `return 5`；
`healthcheck.py` 對「`meta.lastAutoRun.fail` 出現不在 `KNOWN_FAIL` 的來源」判 FAIL。
`meta.lastAutoRun` 是引擎寫的、覆核那一輪不能動（`skills/bubble/SKILL.md` 第 4 步），
所以 Actions 某天偶發一個來源失敗，紅燈會一路留到下一次 Actions 跑完，中間任何覆核交上去都會被 park。
**沒有草稿時 `auto_publish.py` 不跑閘門**，所以這盞紅燈在交件之前不會有徵兆。

處置：
- **不要把偶發失敗加進 `KNOWN_FAIL`**——那會弱化「新失敗來源要被看見」這條設計。
- **也不要為了讓閘門變綠而改 `meta.lastAutoRun`。**
- **等下一次 Actions 跑完**（cron `30 22 * * 1-5`，即平日台北隔天 06:30）**再做覆核**——
  覆核本來就該寫在最新的引擎輸出上；今天做、明天交會把明天的自動數值洗掉。
- 真的連續失敗好幾輪，才是來源修復或白名單的事。

**交付前先跑一次 `healthcheck.py`，FAIL 不是 0 就不要交。**
