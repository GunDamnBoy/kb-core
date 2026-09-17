"""逐字稿的正規化與整段複製偵測。**這是唯一一份實作。**

原本它只住在 `tools/podcast_verify.py` 裡，於是 podfetch 判 `status` 用的是
另一套判準（`collapse_loops`：同一 token 連續 20 次以上）。兩者問的問題不同：

| | 抓什麼 | 2026-08-21 的結果 |
|---|---|---|
| `collapse_loops` | 同一個 token 連著跳針 | oddlots 抓到，判 DEGRADED |
| `block_repeats` | 整段連貫文字被複製兩次 | oddlots ＋ tip 兩處都抓到 |

所以那天 tip 有 172 與 152 token 的整段複製，manifest 仍然判它 `OK` ——
**兩個偵測器給了不同答案，而寬鬆的那一個才是下游會讀到的那一個。**

搬到這裡是為了讓兩邊 import 同一份，而不是各留一份再靠人記得同步：
**這套系統最常見的缺陷類型就是雙軌漂移。**

**上表那句「兩處都抓到」不要讀成「這一類一定抓得到」（2026-09-13 訂正）。**
它記的是 08-21 那一天的結果，而 `block_repeats` 有一個從 08-22 起就存在的盲點：
**行首雙重時間戳會讓它對整段複製完全失效**（成因見下方 `TS_LEAD_RE`）。
2026-08-30 與 09-13 的 twentyvc 各有四段與一段整段複製，兩天都被判「乾淨」。
**「抓什麼」那一欄寫的是它的意圖，不是它的保證。**
"""
import re

# **保留但已不再被使用**（2026-08-22）。**2026-09-13 訂正：本行原寫「真正在跑的是下面的
# `TS_CAP_RE`」，那句現在只對一半** —— `_norm_line` 已改用 `TS_LEAD_RE`（剝行首所有時間戳），
# `TS_CAP_RE` 只剩 `tokens_with_lines()` 取該行的 `stamps` 在用。以下保留原文：真正在跑的是下面的 `TS_CAP_RE`，
# 兩者只差「有沒有捕捉群組」與「吃不吃尾隨空白」。留著是因為它記錄了一件事：
# 舊版整份 body 套 `re.M` 的做法，會讓**連續兩個講者標籤的第二個失去 `^` 錨點**
# （前一次匹配的尾隨 `\s*` 把換行吃掉了），於是那個標籤殘留成內容 token。
# 全庫 26 份逐字稿裡有 1 份踩到（`compound-1000784181722.md`，2 個 token）。
TS_RE = re.compile(r"^\[\d{1,2}[:.]\d{2}(?::\d{2})?\]\s*", re.M)
SPK_RE = re.compile(r"(?:^|\s)Speaker\s*\d+\s*[:\]]\s*", re.M)
NOISE_RE = re.compile(r"[^\w\s]+")


TS_CAP_RE = re.compile(r"^\[(\d{1,2})[:.](\d{2})(?::(\d{2}))?\]")

# **剝掉行首連續的「所有」時間戳，不是只剝第一個**（2026-09-13）。
# `TS_CAP_RE` 沒有 `re.M`、以 `^` 錨定，一行只吃得掉一個；而逐字稿裡會出現
# `[04:35] [04:36] Speaker 2: …` 這種雙重前綴，第二個時間戳於是存活下來，
# 被 `NOISE_RE` 拆成兩個數字 token（`['04','36', …]`）。
#
# **後果不是多兩個雜訊 token，是整段複製偵測整個失效**：那兩個數字在原段與
# 重播段的值不同（差一個偏移量），於是**每一個跨行的 12-gram 都對不上**，
# `block_repeats()` 一段都切不出來、`podcast_dupmap.py` 印「乾淨」。
#
# 全庫 159 份有 7 份帶雙重前綴（最高一份是 09-13 twentyvc，**319／936 body 行＝34.1%**
# ——**分母要標**，同一份用全檔行數算是 33.5%），其中 3 份的偵測結果因此改變：
# 2026-09-13 twentyvc **0 → 1 段／1,618 token**、
# 2026-08-30 twentyvc **0 → 4 段／1,724 token**（**這一集當天判「乾淨」而實際有四段複製，
# 摘譯已發布**）、2026-08-22 oddlots 7 → 13 段。
# **另外 4 份帶雙重前綴但前後都是 0 段** —— 修法揭露既有的複製，不會無中生有。
#
# 誤報風險已量測：**156/159 份行為完全不變，而改變的 3 份全部落在「帶雙重前綴」那 7 份之內**
# ——**是單向包含，不是集合相等**（另外 4 份帶前綴但前後都 0 段）。關鍵性質是反過來說的那一句：
# **沒有任何一份不帶雙重前綴的檔案受影響。**（本註解初版寫「完全重合」，與下一句自相矛盾，同日複驗訂正。）
# （照 `MODIFY.md`「新增檢查」那條，改動前跑全庫）。吃這支的三個消費者
# （`tools/podcast_verify.py`、`tools/podcast_dupmap.py`、`scripts/podcast/podfetch.py`）
# 全在 podcast 之內，沒有別套系統 import `kbcore.transcript`。
#
# **這是上面 `TS_RE` 那個註解記的同一個失效家族的第二例**：`^` 錨定 ＋ 行內重複前綴。
# 那次是連續兩個講者標籤讓第二個失去錨點，這次是連續兩個時間戳。
# **當時只修了講者標籤那一個，沒有人把它推廣到時間戳。**
TS_LEAD_RE = re.compile(r"^(?:\[\d{1,2}[:.]\d{2}(?::\d{2})?\]\s*)+")


def _norm_line(line: str):
    """一行的正規化。**與 `tokens()` 用的是同一組規則，不是另寫一份。**"""
    return NOISE_RE.sub(" ", SPK_RE.sub(" ", TS_LEAD_RE.sub(" ", line)).lower()).split()


def tokens_with_lines(text: str):
    """回傳 `(toks, owners, stamps)`，讓 token 索引可以換算回時間戳。

    - `toks[i]`：第 i 個 token，**與 `tokens()` 逐字相同**（`tokens()` 就是呼叫這一支）
    - `owners[i]`：第 i 個 token 屬於第幾行
    - `stamps[j]`：第 j 行的時間戳秒數，該行沒有時間戳就是 `None`

    **為什麼要有這一支**：`block_repeats()` 回傳的是 token 索引，而 manifest 的警告
    也只印 token 位置。2026-08-22 那一輪，撰寫 subagent 拿到「第 1533 → 第 3791 個字」
    根本無法在逐字稿裡定位，主代理只好臨時寫了一支腳本把它還原成時間戳區間 ——
    那支腳本寫在 `/tmp`，跑完就沒了，隔天那條規則會退回成不可執行。
    **一個每天都要用、卻每天都要重寫的換算，就該是一支工具。**

    **逐行處理與舊版的整份處理「幾乎」等價，那個「幾乎」要講清楚**：
    `TS_LEAD_RE`（2026-09-13 前是 `TS_CAP_RE`）／`SPK_RE` 都是行內樣式，
    而 token 不會跨行，所以絕大多數情況相同。
    改動後以全庫 26 份逐字稿逐檔比對長度與雜湊：**25 份完全一致，1 份差 2 個 token**，
    追下去是**新版修掉了舊版的一個真缺陷**（見上面 `TS_RE` 的註解：
    連續兩個講者標籤時第二個會失去錨點而殘留成內容）。
    **所以這不是「等價」，是「等價再加一個修正」**——寫成等價會讓下一個人以為比對全綠。
    """
    body = text.split("---", 2)[-1]
    toks, owners, stamps = [], [], []
    for j, line in enumerate(body.splitlines()):
        m = TS_CAP_RE.match(line)
        if m:
            h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            stamps.append(h * 3600 + mi * 60 + sec if m.group(3) else h * 60 + mi)
        else:
            stamps.append(None)
        for t in _norm_line(line):
            toks.append(t)
            owners.append(j)
    return toks, owners, stamps


def tokens(text: str):
    """把逐字稿正規化成 token 串：去 front matter、時間戳、講者標記、標點，轉小寫。

    講者標記那條刻意同時吃 `Speaker 6:` 與 `Speaker 6]` —— Bloomberg 那幾集有
    冒號被轉成右方括號的行，只認冒號的話那些行會整行被當成內容。
    """
    return tokens_with_lines(text)[0]


def block_repeats(text: str, k: int):
    """找出整段被複製的區塊。回傳 [{tokens, first, second}]，**門檻不在這裡判。**

    先找重複的 k-gram，再把**位置連續**的併成區塊 —— 單獨一個 k-gram 是慣用語，
    連成一長串才是整段複製。判定門檻交給呼叫端，因為門檻的家在 anchors。
    """
    toks = tokens(text)
    seen, dup = {}, []
    for i in range(len(toks) - k + 1):
        g = " ".join(toks[i:i + k])
        if g in seen:
            dup.append((seen[g], i))
        else:
            seen[g] = i
    out, cur = [], None
    for a, b in dup:
        if cur and a == cur[0] + cur[2] and b == cur[1] + cur[2]:
            cur = (cur[0], cur[1], cur[2] + 1)
        else:
            if cur:
                out.append(cur)
            cur = (a, b, 1)
    if cur:
        out.append(cur)
    return [{"tokens": n + k - 1, "first": a, "second": b} for a, b, n in out]


def cycle_repeats(text: str, k: int, coldopen_head: int,
                  min_copies: int, min_distinct: int, min_group_covered: int = 0):
    """循環重複：**同一段原文被複製到很多處**，而不是被複製到一處。

    這是 `block_repeats()` 從 2026-08-22 起就有、而 anchors 記了三次都沒人實作的那個盲點。
    成因在 `block_repeats()` 的合併條件 `a == cur[0] + cur[2]` —— 它要求重複的兩端同步
    前進，而循環每遇到下一個副本開頭，`seen[g]` 回傳的仍是**第一份**的位置、`a` 因此回捲。
    於是一個重複 443 次的句子被切成 443 個各自低於門檻的小區塊，逐一被濾掉。
    **所以修法不在門檻，在聚合**：按 `first` 分群，同一個 `first` 有 N 份副本就是 N 次循環。

    回傳 `[{first, copies, covered, spans}]`，`covered` 是**副本區間的聯集長度**
    （不是各段相加 —— shingle 會重疊，相加會算出超過全文長度的荒謬值，
    2026-09-17 首版就量到 195%）。門檻不在這裡判，跟 `block_repeats()` 同一條規矩。

    `min_distinct` 濾掉「重複單元只有一兩個相異 token」的那種（`the the the`、`a a a`）——
    **那一種已經由 `quality.stutter_token_repeat` 在計字前剔除了**，這裡再報一次只是噪音。
    留給這一支的是短句級、行級、區塊級三種尺度，也就是文件記了卻沒有任何機械檢查涵蓋的那三種。

    **全庫 181 份的實測（2026-09-17）**：`min_copies=3`、每組覆蓋 `>=100`，
    檔案層級取「覆蓋 `>=3%` **或** 絕對 `>=250` token」，**報 35 份（19.3%）**，
    文件曾具名記過的案例全部命中。抽驗其中約 10 份，都是真的重複
    （`like on like on`、`in a in a`、整段人物介紹循環、整句內容重複數百次）。

    **那 19.3% 應該讀成「汙染率的下界」，不是誤報率，也不是汙染率本身**（09-17 複驗訂正）：
    未觸發的 146 份一份都沒查過，**偽陰性完全沒有量**，兩側沒有同時封住就不能叫汙染率；
    而「零誤報」的樣本是約 10／35，推不到全部。**初版把這三件事都寫過頭了。**

    **`covered` 只算副本區間、不含第一份原文** —— 這個定義直接決定結論：
    09-17 的 iltb 只算副本是 2.89%、含原文是 3.86%，
    **也就是「它需不需要絕對量下限才撈得回來」完全取決於這個定義**。
    """
    toks = tokens(text)
    groups: "dict[int, list]" = {}
    for r in block_repeats(text, k):
        if r["first"] < coldopen_head:
            continue
        groups.setdefault(r["first"], []).append(
            (r["second"], r["second"] + r["tokens"]))
    out = []
    for first, spans in groups.items():
        if len(spans) < min_copies:
            continue
        unit = max(b - a for a, b in spans)
        end = first + unit
        if len(set(toks[first:end])) < min_distinct:
            continue
        merged, cs, ce = 0, None, None
        for s, e in sorted(spans):
            if cs is None:
                cs, ce = s, e
            elif s <= ce:
                ce = max(ce, e)
            else:
                merged += ce - cs
                cs, ce = s, e
        if cs is not None:
            merged += ce - cs
        # **每一組自己的覆蓋量下限。** `block_repeats()` 有 `block_repeat_min_tokens=150`，
        # 而 `block_repeat_source` 明寫那 150 就是為了排除「廣告與台呼 40–79 token」；
        # 按 `first` 聚合之後區塊變小，那道保護就沒了。
        # **但下限不能訂在「單元長度」上** —— 真的循環單元往往也很短
        # （08-30 mib 是同一句重複 443 次、09-02 oddlots 同句 232 行），
        # 2026-09-17 實測單元下限 40 會把九個已知真陽性砍到剩四個。
        # **分辨線是「這一組蓋掉多少內容」**：08-23 mib 那句 14 token 的台呼
        # （`i m barry ritholtz you re listening to masters in business…`）重複四次
        # 只蓋掉 63 token，而真循環動輒數百到數萬。
        if merged < min_group_covered:
            continue
        out.append({"first": first, "copies": len(spans),
                    "covered": merged, "spans": sorted(spans)})
    return sorted(out, key=lambda r: -r["covered"])


def significant_repeats(text: str, k: int, min_tokens: int, coldopen_head: int):
    """套上門檻之後真正該報的那些。

    cold-open 豁免：第一次出現落在前 `coldopen_head` 個 token 之內的，是片頭預告 ——
    **那是片頭預告的定義本身**，不是為了讓數字好看而開的例外。
    """
    return [r for r in block_repeats(text, k)
            if r["tokens"] >= min_tokens and r["first"] >= coldopen_head]
