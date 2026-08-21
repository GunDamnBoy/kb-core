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
"""
import re

# **保留但已不再被使用**（2026-08-22）。真正在跑的是下面的 `TS_CAP_RE`，
# 兩者只差「有沒有捕捉群組」與「吃不吃尾隨空白」。留著是因為它記錄了一件事：
# 舊版整份 body 套 `re.M` 的做法，會讓**連續兩個講者標籤的第二個失去 `^` 錨點**
# （前一次匹配的尾隨 `\s*` 把換行吃掉了），於是那個標籤殘留成內容 token。
# 全庫 26 份逐字稿裡有 1 份踩到（`compound-1000784181722.md`，2 個 token）。
TS_RE = re.compile(r"^\[\d{1,2}[:.]\d{2}(?::\d{2})?\]\s*", re.M)
SPK_RE = re.compile(r"(?:^|\s)Speaker\s*\d+\s*[:\]]\s*", re.M)
NOISE_RE = re.compile(r"[^\w\s]+")


TS_CAP_RE = re.compile(r"^\[(\d{1,2})[:.](\d{2})(?::(\d{2}))?\]")


def _norm_line(line: str):
    """一行的正規化。**與 `tokens()` 用的是同一組規則，不是另寫一份。**"""
    return NOISE_RE.sub(" ", SPK_RE.sub(" ", TS_CAP_RE.sub(" ", line)).lower()).split()


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
    `TS_CAP_RE`／`SPK_RE` 都是行內樣式，而 token 不會跨行，所以絕大多數情況相同。
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


def significant_repeats(text: str, k: int, min_tokens: int, coldopen_head: int):
    """套上門檻之後真正該報的那些。

    cold-open 豁免：第一次出現落在前 `coldopen_head` 個 token 之內的，是片頭預告 ——
    **那是片頭預告的定義本身**，不是為了讓數字好看而開的例外。
    """
    return [r for r in block_repeats(text, k)
            if r["tokens"] >= min_tokens and r["first"] >= coldopen_head]
