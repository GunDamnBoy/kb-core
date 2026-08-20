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

TS_RE = re.compile(r"^\[\d{1,2}[:.]\d{2}(?::\d{2})?\]\s*", re.M)
SPK_RE = re.compile(r"(?:^|\s)Speaker\s*\d+\s*[:\]]\s*", re.M)
NOISE_RE = re.compile(r"[^\w\s]+")


def tokens(text: str):
    """把逐字稿正規化成 token 串：去 front matter、時間戳、講者標記、標點，轉小寫。

    講者標記那條刻意同時吃 `Speaker 6:` 與 `Speaker 6]` —— Bloomberg 那幾集有
    冒號被轉成右方括號的行，只認冒號的話那些行會整行被當成內容。
    """
    body = text.split("---", 2)[-1]
    return NOISE_RE.sub(" ", SPK_RE.sub(" ", TS_RE.sub(" ", body)).lower()).split()


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
