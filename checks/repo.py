"""repo 層級的檢查——看的不是資料，是**這個 repo 本身有沒有寫錯東西**。

跑在 push／PR 上，不是每天跑。它抓的是設定錯誤，設定不會自己漂移，會漂移的是人改它。

payload 形狀：
    {"workflows": [{"path": str, "text": str}],
     "briefs":    [{"path": str, "budget": int|None, "budget_source": str,
                    "est_tokens": int}]}

IO 全部在 `tools/repo_check.py` 裡做，檢查只吃已經讀好的結構。這樣每條檢查都能
用純資料當 fixture，不需要在測試裡造檔案。
"""
from kbcore.check import Check, fail, ok, register, skipped, warn

# 中文 brief 的字元／token 比。出處：2026-08-18 工單 11 實測，投顧 brief
# 38,570 字元 ≈ 35k token。這是**估算**，依規則要標 ~，且禁止在兩個實測點之間內插。
CHARS_PER_TOKEN = 1.1


def _no_pull_request_target(p):
    """`pull_request_target` 在 public repo 是把 secret 交給 fork 的 PR。

    它以 base repo 的身分執行、拿得到 secret，卻可以 checkout fork 的程式碼。
    資料 repo 全部是 public（工單 16），所以這條是硬禁。

    只擋 trigger 位置的用法——字串出現在註解或說明文字裡不算。
    """
    bad = []
    for w in p.get("workflows") or []:
        for i, line in enumerate(w["text"].splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "pull_request_target" in stripped:
                bad.append(f"{w['path']}:{i}")
    if bad:
        return fail("pull_request_target 出現在 " + "、".join(bad) +
                    " —— public repo 用它等於把 secret 交給 fork 的 PR")
    return ok()


register(Check(
    id="repo.no_pull_request_target",
    covers="沒有任何 workflow 使用 pull_request_target",
    blind_to=[
        "用 workflow_run 觸發也能達到類似效果，這條看不到",
        "secret 被 echo 進 log 或寫進 artifact",
        "第三方 action 被釘在可變的 tag 而非 sha",
    ],
    run=_no_pull_request_target,
    fixture={"workflows": [{"path": "w.yml", "text": "on:\n  pull_request_target:\n"}]},
    no_boundary="用了就是用了，沒有「用一點點」這種程度",
    suite="repo",
))


def _brief_budget(p):
    """brief 的 token 預算。

    工單 11 點名的風險：這**可能是一條永遠會 PASS 的檢查**——預算 22k、brief 才
    3k，怎麼寫都過。所以它的 fixture／near_miss 貼著預算線的兩側，自檢會確認它
    在對的地方叫，而不是只確認它會叫。

    投顧的 brief 已經超過它自己記載的截斷點（規格寫 25k token／417 行，實際 35k
    ／560 行），**而沒有任何機制會說**。「加字前先問加完還讀得完嗎」這條紀律實測
    失效——所以它要變成機制。
    """
    briefs = p.get("briefs")
    if not briefs:
        return skipped("這個 repo 沒有 BRIEF.md，該項未執行")
    over, nosource = [], []
    for b in briefs:
        if b.get("budget") is None:
            nosource.append(b["path"])
            continue
        if not b.get("budget_source"):
            nosource.append(b["path"])
        if b["est_tokens"] > b["budget"]:
            over.append(f"{b['path']} ~{b['est_tokens']} token，預算 {b['budget']}")
    if over:
        return fail("；".join(over) + " —— 超過預算就是執行時讀不完，要砍不是要調高")
    if nosource:
        return warn("沒有預算或沒有出處：" + "、".join(nosource) +
                    " —— 沒有出處的數字不算量測過")
    return ok()


register(Check(
    id="repo.brief_budget",
    covers="每份 BRIEF.md 的估算 token 數不超過它自己宣告的預算，且預算有出處",
    blind_to=[
        "字元／token 比是估算，中英混排會偏",
        "沒超過預算但內容重複囉唆",
        "brief 沒超過，但 brief ＋ skill ＋ preamble 加起來超過",
        "預算數字本身訂得太寬鬆",
    ],
    run=_brief_budget,
    fixture={"briefs": [{"path": "BRIEF.md", "budget": 1000,
                         "budget_source": "測試", "est_tokens": 1001}]},
    near_miss={"briefs": [{"path": "BRIEF.md", "budget": 1000,
                           "budget_source": "測試", "est_tokens": 1000}]},
    suite="repo",
))
