"""Houseview 月報的檢查。**這一套沒有 System，也不走發布軌。**

月報的產出是一份交給同仁的 pptx，不是 `data/<date>.json`，所以
`kbcore/system.py` 那組欄位（`build`／`index_entry`／`staged_paths`／
`cadence_hours`／`republish_rule`）一個都用不上。`run_all(payload, suite)`
只認 suite、不需要 System —— 這條路本來就通，不必為月報改底盤。

入口是 `tools/houseview_verify.py`（只讀不寫）。

## 為什麼從 `healthcheck_hv.py` 搬過來

那支 753 行的腳本**修過三處「永遠會 PASS 的檢查」**（brief 與產生器兩邊同時
消失時一行都不印、焦點頁位置檢查在頁數 > 2 時被整段跳過、`chs.index("策略")`
取第一個誤判），三次都是人抓到的。`Check` 契約的 `fixture`／`near_miss`
把這件事從紀律變成機制：**自檢會擋掉觸發不了自己 fixture 的檢查。**

## 「61 項」是輸出行數，不是斷言數

2026-08-23 逐條盤點的結果是 **117 條斷言**。61 是全綠時的 PASS 行數，它藏掉了
25 條匯流成單行 PASS 的 payload 規則、5 條只印一行的 brief 章節、
以及 25 條沒有 PASS 分支的 fail-only 檢查；而且 61 還會浮動
（2026-08 沒有上一期 → 60 行、legacy 期別 → 58 行）。

**規格寫著「健康檢查項目數只增不減是刻意的」，而那個被追蹤的數字量的是
stdout 行數。** 搬過來之後每一條都是一個 Check 物件，`len(REGISTRY)` 就是斷言數。

## payload 形狀

    {"period": "2026-08", "v3": bool,
     "files":   {檔名: bool},              # 有沒有這個檔
     "build_src": str|None,                # build_hv3.js 全文
     "build_syntax": {"ok": bool, "err": str}|None,   # None ＝ 這台機器沒有 node
     "brief":   str|None,                  # HOUSEVIEW_BRIEF.md 全文
     "content": dict,                      # 本期 content JSON
     "prev":    dict|None,                 # 上一期
     "chartkit": str|None,                 # chart-of-the-day/tools/chartkit.py 全文
     "images":  {相對路徑: bool}}          # image 區塊指到的檔在不在

IO 全部在 `tools/houseview_verify.py`，**檢查一律不做 IO** —— 那樣每條檢查
才能用純資料當 fixture，不必在測試裡造一個 repo。
"""
from kbcore.check import Check, fail, ok, register, skipped

SUITE = "houseview"


# ══════════════════════════════════════════════════════════════
# 第 1 段：檔案齊全
# ══════════════════════════════════════════════════════════════

def _reg_file(name, why, blind):
    ident = "houseview.file_" + name.replace(".", "_").replace("-", "_").lower()

    def run(p, _n=name):
        have = (p.get("files") or {}).get(_n)
        if have is None:
            return skipped(f"payload 沒有 `files[{_n!r}]` —— 這條沒有被執行過")
        return ok() if have else fail(f"{_n} 不存在 —— {why}")

    register(Check(
        id=ident, covers=f"`{name}` 在位。{why}", blind_to=blind, run=run,
        fixture={"files": {name: False}},
        no_boundary="檔案在或不在，沒有中間狀態",
        suite=SUITE))


_reg_file("build_hv3.js", "現行產生器不在，版面常數與鐵律那 19 條會全部驗不到",
          ["檔案在，但內容被換成別的東西 —— 那由第 3、4 段的字串比對抓",
           "檔案在，但 node 跑不起來 —— 那是 `generator_v3_syntax` 的事"])
_reg_file("build_hv.js", "凍結的 legacy 產生器不在，2026-07 以前的期別重建不出來；"
          "而且 `find_dir()` 拿它當工作目錄的判準檔，刪掉它整支檢查會找不到自己",
          ["它的語法沒有任何人在驗 —— 舊 healthcheck 只 `node --check` v3 那支"])
_reg_file("HOUSEVIEW_BRIEF.md", "規格文件不在，第 6 段那 22 條同步比對全部驗不到",
          ["它在、但內容過期 —— 那由第 6 段抓，而第 6 段抓不到「兩邊同時改錯」"])
_reg_file("style-exemplar.md", "縱深寫法的範本不在，「寫到什麼程度才算數」就沒有對照樣本",
          ["範本在，但寫作有沒有真的照它 —— 機器驗不了，見 `depth_history_years`"])


# ══════════════════════════════════════════════════════════════
# 第 2 段：產生器語法
# ══════════════════════════════════════════════════════════════

def _syntax(p):
    st = p.get("build_syntax")
    if st is None:
        return skipped(
            "這台機器上找不到 node，語法沒有被檢查。**這不是通過** —— "
            "月報是手動啟動、產生器要在有 node 的環境跑，"
            "所以這條跳過代表這台機器現在產不出 pptx")
    if st.get("ok"):
        return ok()
    return fail(f"build_hv3.js 語法錯誤：{(st.get('err') or '')[:200]}")


register(Check(
    id="houseview.generator_v3_syntax",
    covers="`build_hv3.js` 過得了 `node --check`，不會等到當月產出時才炸",
    blind_to=[
        "語法對、行為錯 —— `node --check` 只解析不執行",
        "**legacy 的 `build_hv.js` 完全沒有語法檢查**（舊 healthcheck 就沒有，照搬）",
        "node 版本差異造成的語法可用性（`?.`／`??` 在舊版會炸）",
    ],
    run=_syntax,
    fixture={"build_syntax": {"ok": False, "err": "SyntaxError: Unexpected token"}},
    no_boundary="解析得過或不過，沒有中間狀態",
    suite=SUITE))


# ══════════════════════════════════════════════════════════════
# 第 3、4 段：版面常數與鐵律
#
# 兩張表逐列一條 Check，**不合併成一條**。合併的樣子就是舊腳本那個
# 「25 條規則匯流成一行 PASS」—— 一條檢查只講它最嚴重的發現，
# 等於把其餘的藏在後面。
# ══════════════════════════════════════════════════════════════

def _reg_source(ident, pat, name, gone, blind):
    import re as _re
    rx = _re.compile(pat)

    def run(p, _rx=rx, _n=name):
        src = p.get("build_src")
        if src is None:
            return skipped(f"`build_hv3.js` 不在，「{_n}」沒有被檢查過 —— "
                           "**這不是通過**。舊腳本在這裡是整段不印，"
                           "於是 19 條同時消失而輸出看起來只是短了一點")
        return ok() if _rx.search(src) else fail(gone)

    register(Check(
        id=ident, covers=name, blind_to=blind, run=run,
        fixture={"build_src": "// 這份原始碼裡沒有那個字串"},
        no_boundary="字串在或不在，沒有中間狀態",
        suite=SUITE))


# ── 版面常數：**這一批暫時拿掉** ────────────────────────────
#
# 舊 healthcheck 有 9 條，逐字比對 `const W = 13.333, H = 7.5`／`const COLS = 3`
# 之類。2026-08-23 對照組員 08-20 的實作檔之後，**那組常數本身是錯的**：
# 實際交付的檔是 10×5.625、2×2 象限、每頁 2.5 張圖，而 v3 規格寫的是
# 13.333×7.5、三欄、每頁 0.8 張。
#
# **把錯的值鎖起來比不鎖更糟** —— 它會讓每一次往正確方向的修正都變成 FAIL。
# 等版面對齊的那一版落地，這裡再依「不寫死」的原則重寫：
# 該鎖的是「畫布與模板一致」「紅色只出現在該出現的地方」這類**關係**，
# 不是某一組座標數字。

_RULE_BLIND = [
    "**只驗那段程式還在，不驗它做對了** —— 函式名在、實作被改壞，這條照樣 PASS",
    "鐵律 1（y 由內容推算）與鐵律 9（規格框列高隨內容）沒有可靠的靜態特徵，"
    "這兩條完全不在這裡，只能靠逐頁看圖抓",
]

for _id, _pat, _name in [
    ("rule_cataxis",   r"catAxisLabelPos: 'low'",  "含負值長條圖的類別標籤推到軸低端"),
    ("rule_fitsize",   r"function fitSize",        "文字區塊自動縮字級"),
    ("rule_bullets",   r"function drawBullets",    "自繪圓點（避免紅字造成條列碎裂）"),
    ("rule_cjk_ratio", r"0\.94",                   "中文行數估算的安全係數"),
    ("rule_r1top",     r"r1Top",                   "第二列起點跟著第一列實際結束"),
    ("rule_validate",  r"function validateContent", "產出前擋掉越界的區塊配置（不靜默漏畫）"),
    ("rule_prose",     r"function drawProse",      "散文段落渲染器（投行體例的正文）"),
    ("rule_bodytop",   r"let bodyTop = 1\.62",     "導言列（lede）之下的動態內文起點"),
    ("rule_exhibit",   r"let EXHIBIT = 0",         "圖表編號（散文可指涉「見圖表 N」）"),
    ("rule_dropped",   r"DROPPED",                 "放不下的內容讓 build 失敗而非默默消失"),
]:
    _reg_source("houseview." + _id, _pat, "版面鐵律：" + _name,
                f"版面鐵律已消失：{_name} —— 這一條拿掉必定出現壓字或死白", _RULE_BLIND)


# ══════════════════════════════════════════════════════════════
# 逐頁講稿
#
# 2026-08-23 新增。月報的產出從一份變兩份，而**深度住在講稿裡**，
# 不在投影片上 —— 理由見 `skills/houseview/SKILL.md` §0.5：
# v3 為了把「2–4 段散文」塞進投影片，去改造了畫布、格線與密度，
# 而組員的舞台沒有跟著改。
#
# 這一組是這次改動最大的收穫：**九手法第一次真的驗得動。**
# 舊規格只能驗代理指標（「散文含歷史年份的章數 ≥4」），因為投影片
# 根本沒地方放縱深。講稿有。
#
# payload 多兩個鍵：
#     "script":  {…}   逐頁講稿 JSON
#     "content": {…}   同一期的投影片 JSON（用來比對頁面對得上）
# ══════════════════════════════════════════════════════════════

# 九個章內手法 ＋ 一個全冊手法。**這裡是唯一的正本。**
#
# 舊規格把名單放在 brief，並用「每個名稱要在 brief 出現 ≥2 次、
# 掉到 1 就 FAIL」當漂移偵測 —— 那是**沒有機器可讀正本時的替代品**。
# 現在有了：brief 反過來對這份名單驗（`brief_device_vocab`）。
DEVICES = (
    "歷史前例錨定",
    "類比之後給反類比",
    "機構行為模式",
    "罕見度量尺",
    "歷史警語",
    "指標失效檢驗",
    "學理框架錨定",
    "前例提煉判讀規則",
    "層級升格",
)
DEVICE_BOOK = "三數字定錨"          # 全冊層級，不算在逐頁的九個裡
MIN_DEVICE_KINDS = 6                # 全冊至少出現過幾種不同手法
MIN_SCRIPT_CHARS = 900              # 每頁【講稿】字數下限，見 `script_depth`

# 把判斷推給讀者的收尾。標題那條禁用詞是「回顧／展望／概況…」，
# 這一組是它在**金句與落地**上的對應物 —— 同一個病、不同的位置。
HEDGE = ("值得持續觀察", "值得留意", "須留意風險", "值得關注",
         "有待觀察", "後續觀察", "審慎以對", "審慎因應")


def _pages(p):
    return ((p.get("script") or {}).get("pages")) or []


def _reg(ident, covers, blind, run, fixture, near_miss=None, no_boundary=""):
    register(Check(id=ident, covers=covers, blind_to=blind, run=run,
                   fixture=fixture, near_miss=near_miss,
                   no_boundary=no_boundary, suite=SUITE))


def _each(p, get, bad_msg, ok_when=None):
    """逐頁跑同一條規則，把**所有**壞掉的頁都列出來。

    只回報第一個壞掉的頁，跟只印一行 PASS 是同一個病的兩面：
    修完第一個以為修完了，下一輪再撞第二個。
    """
    pages = _pages(p)
    if not pages:
        return skipped("payload 沒有 `script.pages` —— 這一組檢查沒有被執行過")
    bad = [f"{pg.get('no', '?')}｜{(pg.get('title') or '')[:24]}：{why}"
           for pg in pages for why in [get(pg)] if why]
    return fail(bad_msg + "　" + "；".join(bad)) if bad else ok()


# ── 四區塊在不在 ────────────────────────────────────────────

def _quote(p):
    return _each(p, lambda pg: "" if (pg.get("quote") or "").strip() else "缺【金句】",
                 "有頁面缺【金句】——那一頁沒有一句可以說出口的話：")


_reg("houseview.script_quote_present",
     "每一頁都有【金句】",
     ["金句在、但它是敘述句不是判斷句 —— 那由 `script_quote_is_judgment` 抓",
      "金句在、但與該頁內容無關 —— 機器驗不了"],
     _quote,
     fixture={"script": {"pages": [{"no": "P1", "quote": ""}]}},
     no_boundary="欄位有內容或沒有，沒有中間狀態")


def _quote_judgment(p):
    def why(pg):
        q = (pg.get("quote") or "").strip()
        hit = [h for h in HEDGE if h in q]
        return f"金句以「{hit[0]}」這類詞收尾，那是把判斷推給讀者" if hit else ""
    return _each(p, why, "有頁面的【金句】沒有表態：")


_reg("houseview.script_quote_is_judgment",
     "【金句】不用「值得持續觀察」這類把判斷推給讀者的寫法",
     ["**詞表擋得住句式，擋不住空話** —— 一句沒有這些詞、但同樣沒有主張的金句照樣 PASS",
      "反諷或引用他人原話裡出現這些詞會被誤判"],
     _quote_judgment,
     fixture={"script": {"pages": [{"no": "P1", "quote": "AI 資本支出值得持續觀察"}]}},
     near_miss={"script": {"pages": [{"no": "P1", "quote": "投入端在加速，而承擔調整的人正在換位"}]}})


def _landing(p):
    return _each(p, lambda pg: "" if (pg.get("landing") or []) else "缺【落地】",
                 "有頁面缺【落地】——那一頁沒有說出對配置的含義：")


_reg("houseview.script_landing_present",
     "每一頁都有【落地】。**內容依題材自由編排**，不固定分類",
     ["落地在、但沒有具體到資產類別 —— 機器驗不了，只能靠人看",
      "**舊規格要求每頁都要點台股，這裡沒有** —— 那條在區域與產業章成立，"
      "在利率或原油章會逼出硬掰的連結"],
     _landing,
     fixture={"script": {"pages": [{"no": "P1", "landing": []}]}},
     no_boundary="有沒有這一塊，沒有中間狀態")


# ── 可證偽條件 ──────────────────────────────────────────────

def _fals_present(p):
    return _each(p, lambda pg: "" if (pg.get("falsifiers") or []) else "缺【可證偽條件】",
                 "有頁面缺【可證偽條件】——沒有門檻的判斷沒辦法進【驗收】記分卡：")


_reg("houseview.script_falsifier_present",
     "每一頁都有【可證偽條件】，這一格直接餵進【驗收】記分卡",
     ["條件在、但永遠不會被觸發（門檻訂得太寬）—— 機器驗不了",
      "條件在、但與該頁的判斷無關"],
     _fals_present,
     fixture={"script": {"pages": [{"no": "P1", "falsifiers": []}]}},
     no_boundary="有沒有這一塊，沒有中間狀態")


def _fals_threshold(p):
    import re
    num = re.compile(r"\d")

    def why(pg):
        bad = [f.get("threshold", "")[:20] for f in (pg.get("falsifiers") or [])
               if not num.search(str(f.get("threshold", "")))]
        return f"{len(bad)} 條門檻沒有數字（{'、'.join(bad)}）" if bad else ""
    return _each(p, why, "有可證偽條件沒有數字門檻——「布蘭特能否守住低點區間」那種寫法擋不住任何東西：")


_reg("houseview.script_falsifier_has_number",
     "每一條【可證偽條件】的門檻都帶數字",
     ["有數字、但方向沒寫（升破還是跌破）—— 這條看不到",
      "上游 `watch` 的原句常常只有事件名沒有數字，沿用前要補；**這條就是那個補的守門**"],
     _fals_threshold,
     fixture={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "布蘭特能否守住低點區間"}]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "capexocf 跌破 75%"}]}]}})


def _fals_primary(p):
    def why(pg):
        fs = pg.get("falsifiers") or []
        if not fs:
            return ""
        n = sum(1 for f in fs if f.get("primary"))
        if n == 1:
            return ""
        return f"{n} 條標成 primary（要恰好 1 條）"
    return _each(p, why, "【可證偽條件】沒有指定主要的那一條——都一樣重要等於都不重要：")


_reg("houseview.script_falsifier_one_primary",
     "每一頁的【可證偽條件】恰好一條標成 `primary`",
     ["標對了一條、但標錯了哪一條 —— 機器驗不了"],
     _fals_primary,
     fixture={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "1", "primary": True}, {"threshold": "2", "primary": True}]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "1", "primary": True}, {"threshold": "2"}]}]}})


def _fals_now(p):
    def why(pg):
        bad = [str(f.get("threshold", ""))[:16] for f in (pg.get("falsifiers") or [])
               if not str(f.get("now", "")).strip()]
        return f"{len(bad)} 條沒有現值" if bad else ""
    return _each(p, why, "有可證偽條件沒有寫現值——不知道離門檻多遠的門檻沒有用：")


_reg("houseview.script_falsifier_has_now",
     "每一條【可證偽條件】都寫了現值",
     ["現值在、但過期 —— 這條看不到，要靠 `prep` 的取數日期人工對"],
     _fals_now,
     fixture={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "跌破 75%", "now": ""}]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "falsifiers": [
         {"threshold": "跌破 75%", "now": "81.8%"}]}]}})


# ── 縱深手法 ────────────────────────────────────────────────

def _dev_declared(p):
    return _each(p, lambda pg: "" if (pg.get("devices") or []) else "沒有自報任何縱深手法",
                 "有頁面沒有自報縱深手法：")


_reg("houseview.script_devices_declared",
     "每一頁都自報至少一個縱深手法",
     ["**自報不等於做到** —— 這條驗的是有沒有交代，不是寫得好不好。"
      "手法的品質機器驗不了，九手法本身也是從**樣本數 1** 的講稿歸納的"],
     _dev_declared,
     fixture={"script": {"pages": [{"no": "P1", "devices": []}]}},
     no_boundary="有沒有自報，沒有中間狀態")


def _dev_vocab(p):
    ok_set = set(DEVICES) | {DEVICE_BOOK}

    def why(pg):
        bad = [d for d in (pg.get("devices") or []) if d not in ok_set]
        return f"手法名稱不在名單內：{'、'.join(bad)}" if bad else ""
    return _each(p, why, "有頁面自報了名單外的手法名稱——名字自由發揮，全冊涵蓋度就算不出來：")


_reg("houseview.script_devices_in_vocab",
     f"自報的手法名稱都在九手法名單內（{'、'.join(DEVICES)}；全冊層級：{DEVICE_BOOK}）",
     ["名稱對、但那一段其實沒有用到該手法 —— 機器驗不了"],
     _dev_vocab,
     fixture={"script": {"pages": [{"no": "P1", "devices": ["深入分析"]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "devices": ["層級升格"]}]}})


def _dev_coverage(p):
    pages = _pages(p)
    if not pages:
        return skipped("payload 沒有 `script.pages`")
    kinds = {d for pg in pages for d in (pg.get("devices") or []) if d in DEVICES}
    if len(kinds) >= MIN_DEVICE_KINDS:
        return ok()
    return fail(f"全冊只用到 {len(kinds)} 種不同的縱深手法（門檻 {MIN_DEVICE_KINDS}）："
                f"{'、'.join(sorted(kinds))} —— 少的那幾種是"
                f"{'、'.join(sorted(set(DEVICES) - kinds))}")


_reg("houseview.script_devices_coverage",
     f"全冊至少出現過 {MIN_DEVICE_KINDS} 種不同的縱深手法",
     ["**種類夠、但集中在少數幾頁** —— 這條只數種類，不看分布",
      "全部集中在同一章也照樣 PASS"],
     _dev_coverage,
     fixture={"script": {"pages": [{"no": "P1", "devices": ["層級升格", "罕見度量尺"]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "devices": list(DEVICES[:6])}]}})


# ── 深度的代理指標 ──────────────────────────────────────────

def _depth(p):
    def why(pg):
        n = sum(len(x) for sec in (pg.get("script") or [])
                for x in (sec.get("paras") or []))
        return f"【講稿】只有 {n} 字（下限 {MIN_SCRIPT_CHARS}）" if n < MIN_SCRIPT_CHARS else ""
    return _each(p, why, "有頁面的【講稿】太短——這是深度的代理指標，短到這個程度通常是在唸圖上的數字：")


_reg("houseview.script_depth",
     f"每一頁【講稿】至少 {MIN_SCRIPT_CHARS} 字",
     ["**字數是代理指標，不是深度** —— 一頁一千字的複述照樣 PASS，"
      "而真正的深度（機制、前例、二階效應）機器量不到",
      "過場頁（⏩）也照這個門檻，可能過嚴 —— 第一期跑完看實際分布再調"],
     _depth,
     fixture={"script": {"pages": [{"no": "P1", "script": [{"paras": ["短"]}]}]}},
     near_miss={"script": {"pages": [{"no": "P1", "script": [
         {"paras": ["字" * MIN_SCRIPT_CHARS]}]}]}})


# ── 三數字定錨 ──────────────────────────────────────────────

def _anchor3(p):
    sc = p.get("script") or {}
    if "anchor3" not in sc:
        return skipped("payload 沒有 `script.anchor3`")
    a = sc.get("anchor3") or []
    if len(a) == 3:
        return ok()
    return fail(f"三數字定錨有 {len(a)} 個（要恰好 3 個）—— "
                "頭尾呼應靠的是同樣那三個數字，多一個少一個都接不起來")


_reg("houseview.script_anchor3_count",
     "全冊的三數字定錨恰好三個",
     ["三個在、但沒有在【策略】章回收 —— 那由 `script_anchor3_recycled` 抓",
      "三個數字本身選得好不好，機器驗不了"],
     _anchor3,
     fixture={"script": {"anchor3": ["a", "b"], "pages": []}},
     near_miss={"script": {"anchor3": ["a", "b", "c"], "pages": []}})


# ── 講稿與投影片對得上（先講稿後排版）──────────────────────

def _align(p):
    sc = _pages(p)
    ct = (p.get("content") or {}).get("pages")
    if not sc or ct is None:
        return skipped("缺 `script.pages` 或 `content.pages` —— 這條沒有被執行過")
    st = [(pg.get("title") or "").strip() for pg in sc]
    cttl = {(pg.get("title") or "").strip() for pg in ct}
    miss = [t for t in st if t and t not in cttl]
    extra = [t for t in (x for x in cttl if x) if t not in st]
    if not miss and not extra:
        return ok()
    msg = []
    if miss:
        msg.append(f"講稿有、投影片沒有：{'、'.join(t[:20] for t in miss)}")
    if extra:
        msg.append(f"投影片有、講稿沒有：{'、'.join(t[:20] for t in extra)}")
    return fail("；".join(msg) + " —— **順序是先寫講稿再排版**，"
                "投影片多出來的那幾頁代表有頁面沒有想過要講什麼")


_reg("houseview.script_content_aligned",
     "講稿與投影片的頁面一一對應（以標題比對）",
     ["標題相同、但講的不是同一件事 —— 機器驗不了",
      "**這條假設標題逐字相同**。排版時修了標題卻沒回頭改講稿，"
      "會被判成不對齊 —— 那是對的，因為標題是判斷句，改了就是改了判斷"],
     _align,
     fixture={"script": {"pages": [{"title": "甲"}]}, "content": {"pages": [{"title": "乙"}]}},
     near_miss={"script": {"pages": [{"title": "甲"}]}, "content": {"pages": [{"title": "甲"}]}})


# ── brief 對回這份名單（取代舊的「出現 ≥2 次」漂移偵測）────

def _brief_vocab(p):
    b = p.get("brief")
    if b is None:
        return skipped("`HOUSEVIEW_BRIEF.md` 不在，名單沒有被對過")
    miss = [d for d in DEVICES + (DEVICE_BOOK,) if d not in b]
    if miss:
        return fail(f"brief 裡找不到這幾個手法名稱：{'、'.join(miss)} —— "
                    "名單的正本在 `checks/houseview.py` 的 `DEVICES`，brief 要跟它一致")
    return ok()


_reg("houseview.brief_device_vocab",
     "`HOUSEVIEW_BRIEF.md` 提到的手法名稱與 `DEVICES` 正本一致",
     ["brief 多寫了名單外的手法 —— 這條只驗「正本裡的都有」，不驗「沒有多的」",
      "**方向是 brief 對回程式，不是程式對回 brief**。舊規格用「每個名稱在 brief "
      "出現 ≥2 次、掉到 1 就 FAIL」當漂移偵測，那是沒有機器可讀正本時的替代品"],
     _brief_vocab,
     fixture={"brief": "這份 brief 沒有提到任何手法名稱"},
     no_boundary="名單裡的每一個名稱在或不在，沒有中間狀態")


def _anchor3_recycled(p):
    """三個定錨數字要在【策略】章收尾時回收。

    **頭尾呼應不是修辭，是讓 20 頁讀起來是一個論證而不是 20 個判斷。**
    比對方式是子字串：定錨句裡的**數字部分**有沒有出現在【策略】那一頁。
    """
    import re
    sc = p.get("script") or {}
    a = sc.get("anchor3")
    if not a:
        return skipped("payload 沒有 `script.anchor3`")
    strat = [pg for pg in _pages(p) if pg.get("chapter") == "策略"]
    if not strat:
        return skipped("這一期沒有【策略】章 —— 回收無從驗起。"
                       "**這不是通過**：少了收尾章，三數字定錨只做了一半")
    body = " ".join(x for pg in strat
                    for sec in (pg.get("script") or []) for x in (sec.get("paras") or []))
    body += " " + " ".join(x for pg in strat for x in (pg.get("landing") or []))
    miss = []
    for s in a:
        nums = re.findall(r"[\d][\d,\.]*", str(s))
        if nums and not any(n in body for n in nums):
            miss.append(str(s)[:28])
    if miss:
        return fail("【策略】章沒有回收這幾個定錨數字：" + "、".join(miss)
                    + " —— 頭尾用的必須是同樣那三個數字，換一組就接不起來")
    return ok()


_reg("houseview.script_anchor3_recycled",
     "三數字定錨在【策略】章被回收（以數字子字串比對）",
     ["**只比數字字串在不在，不比它有沒有被好好收回來** —— 把三個數字重念一遍照樣 PASS",
      "定錨句沒有數字時這條跳過那一句 —— 沒有數字的定錨本來就不該存在，但這裡不擋"],
     _anchor3_recycled,
     fixture={"script": {"anchor3": ["營建支出年增 46%"],
                         "pages": [{"chapter": "策略", "script": [{"paras": ["收尾沒有提到那個數字。"]}]}]}},
     near_miss={"script": {"anchor3": ["營建支出年增 46%"],
                           "pages": [{"chapter": "策略", "script": [{"paras": ["回到開場那三個數字：年增 46%。"]}]}]}})
