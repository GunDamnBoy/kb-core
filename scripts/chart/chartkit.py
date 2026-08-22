# -*- coding: utf-8 -*-
"""
chartkit — 每日五圖的繪圖引擎。

單一事實來源原則：每張圖只寫一次「資料 + 語意」，
本模組同時吐出 (a) 靜態 PNG/SVG（matplotlib）與 (b) ECharts option（互動網頁）。
兩軌若不同源就會漂移，所以永遠只從同一個 Series 物件出發。
"""
from __future__ import annotations
import json, math, os, datetime as dt
from dataclasses import dataclass, field, replace as ck_replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Wedge
from matplotlib.ticker import FuncFormatter
import matplotlib.dates as mdates

# ---------------------------------------------------------------- 樣式
INK      = "#14161A"
MUTED    = "#6B7076"
FAINT    = "#9BA0A6"
GRID     = "#E7E5E2"
RULE     = "#C9C5C0"
BG       = "#FFFFFF"
# ── 序列色：角色制，不是編號制 ────────────────────────────────
# 顏色回答的是「你在這張圖的論證裡是什麼角色」，不是「你是第幾條序列」。
# 每張圖都有 takeaway 與 so_what，也就是每張圖都在講一句話——
# 顏色的工作是讓人一眼看出那句話講的是哪一條線。
#
# ACCENT 的舊值 #C8102E 註解寫著「台新紅」，但那不是台新紅。
# 品牌紅取自 tsholdings.com.tw 的 logo SVG fill（全站計算樣式 86 處）＝ #D70C18。
# #C8102E 接近 Pantone 186，是當初挑錯的；#C00000 則是 PowerPoint 標準色盤的
# Dark Red，House View 模板用的是那個。三者兩兩相距 ΔE 6～8——
# 都在「太近讀不出是刻意的、太遠又不像同一個顏色」的最糟區間。
# 這裡與 House View 月報統一到品牌紅，下游貼 PNG 時才不會出現兩種紅。
ACCENT   = "#D70C18"        # 主角：品牌紅。只留給主角線／今日點，一張圖只有一個
REF      = "#1F4E79"        # 對照：深藍。前期、對手、共識
ALT      = "#8A8F95"        # 溢出：中灰。第三條。用到就代表該考慮拆圖了
DIM      = "#B8BBBE"        # 背景：淺灰。其餘所有東西，低對比是刻意的
PALETTE  = [ACCENT, REF, ALT, DIM]
# 原本的土黃 #D9942B／綠 #3F7D5C／紫 #7A6BA8 已移出工作集：
#   土黃對白底只有 2.6:1，2pt 細線會偏淡；綠與 ACCENT 在紅綠色盲下只差 17。
#   更重要的是，一張圖需要第 5、6 個顏色時，該修的是圖不是色。
#
# 正負值不分色。原本的 POS/NEG 是死碼——全 repo 從未被引用，
# 而且 NEG 的值與 ACCENT 完全相同，真用起來會讓紅同時代表「重點」與「下跌」。
# 正負一律靠 zero_line（見 Chart.zero_line）與資料標籤表達，
# 紅只保留給主角。這也順帶避開台灣紅漲綠跌與西方慣例相反的問題。

CJK = ["PingFang TC", "Noto Sans CJK TC", "Noto Sans TC", "Heiti TC",
       "Microsoft JhengHei", "Noto Sans CJK JP", "DejaVu Sans"]

_FONT_READY = False
_CACHE = os.path.expanduser("~/.cache/chart-of-the-day/fonts")


def _ensure_cjk_font():
    """確保 matplotlib 找得到繁中字型。

    macOS 有 PingFang TC，直接可用。Linux 通常只有 Noto Sans CJK 的 .ttc 集合檔，
    而 matplotlib 只會登記 .ttc 的第一個 face（日文），造成繁中字形被日文字形取代。
    因此在找不到繁中字型時，用 fontTools 把 TC face 抽出到使用者快取目錄再登記。
    **抽出的檔案放快取、不放 repo**——單檔 17MB，不應進版控。
    """
    global _FONT_READY
    if _FONT_READY:
        return
    import matplotlib.font_manager as fm
    have = {f.name for f in fm.fontManager.ttflist}
    if have & {"PingFang TC", "Noto Sans CJK TC", "Noto Sans TC", "Heiti TC"}:
        _FONT_READY = True
        return
    os.makedirs(_CACHE, exist_ok=True)
    for cached, src, idx in [
        (f"{_CACHE}/NotoSansCJKtc-Regular.otf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 3),
        (f"{_CACHE}/NotoSansCJKtc-Bold.otf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 3),
    ]:
        try:
            if not os.path.exists(cached):
                if not os.path.exists(src):
                    continue
                from fontTools.ttLib import TTCollection
                TTCollection(src).fonts[idx].save(cached)
            fm.fontManager.addfont(cached)
        except Exception as e:                       # 抽不出來就退回泛 CJK face
            print(f"  [font] 繁中字型準備失敗，改用備援：{e}")
    _FONT_READY = True


def apply_style():
    _ensure_cjk_font()
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "font.family": "sans-serif", "font.sans-serif": CJK,
        "axes.edgecolor": RULE, "axes.linewidth": 0.9,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.labelcolor": MUTED, "text.color": INK,
        "axes.unicode_minus": False, "figure.dpi": 200,
        # 讓 SVG 的內部 id 由固定 salt 產生：同一份 JSON 重畫要能位元級重現，
        # 否則「歷史可重建」無法被機械驗證，只能靠肉眼看。
        "svg.hashsalt": "chart-of-the-day",
    })

# ---------------------------------------------------------------- 資料容器
@dataclass
class Series:
    name: str
    dates: list          # 'YYYY-MM-DD'
    values: list
    color: str = None
    axis: str = "left"   # left | right
    style: str = "line"  # line | area | bar
    width: float = 1.9
    dash: bool = False
    derived: bool = False   # 滾動波動率、移動平均這類「由別的序列算出來」的量。
                            # 它們的單日跳動來自窗口進出，不是市場事件，
                            # QA 檢查會照抓但標成 derived，處置方式不同（見 qa_series）。

@dataclass
class Marker:
    date: str
    label: str
    color: str = FAINT

@dataclass
class Chart:
    slug: str
    title: str
    subtitle: str
    series: list = field(default_factory=list)
    markers: list = field(default_factory=list)
    # timeseries | scatter | waterfall | grouped_bar | stacked_bar | range_area | heatmap | gauge
    kind: str = "timeseries"
    y_label: str = ""
    y2_label: str = ""
    y_fmt: str = "{:,.0f}"
    y2_fmt: str = "{:,.2f}"
    source: str = ""
    note: str = ""
    zero_line: bool = False
    y_log: bool = False          # 利差、倍數這類「比例才有意義」的量請開啟
    # scatter 專用
    pts: list = field(default_factory=list)      # [(x, y), ...]
    hi_pts: list = field(default_factory=list)   # [(x, y, label), ...]
    x_label: str = ""
    # ── 非時間序列圖型共用（2026-08-09 新增，見 AGENT_BRIEF 第 4 節「圖型跟著問題走」）
    cats: list = field(default_factory=list)     # 類別軸標籤
    vals: list = field(default_factory=list)     # 單一數列（waterfall／gauge 用）
    groups: list = field(default_factory=list)   # [{"name":..,"values":[..]}, ...]
    total_label: str = ""                        # waterfall 末端合計欄的名稱；空字串＝不畫
    band: list = field(default_factory=list)     # range_area：[(date, lo, hi), ...]
    band_label: str = ""                         # 區間帶的圖例名稱（例如「近十年區間」）
    matrix: list = field(default_factory=list)   # heatmap：二維數值
    rows: list = field(default_factory=list)     # heatmap 列標籤
    gauge: dict = field(default_factory=dict)    # {"value":..,"lo":..,"hi":..,"ref":..}

_label_slots: dict = {}


def _fit_ticks(ax, cats, rotate_ok=True):
    """類別標籤依每一格的可用寬度斷行；還是塞不下就縮字級。

    **標籤糊成一團跟沒有標籤一樣糟，而且更難發現** —— 圖看起來是完整的。
    """
    cats = [str(c) for c in cats]
    n = max(1, len(cats))
    slot = TICK_W / n
    longest = max((_vis_len(c) for c in cats), default=0)
    size = 9.0
    if longest > slot * 3:          # 三行還放不下 → 縮字級，等比放寬每行容量
        size = max(6.5, 9.0 * (slot * 3) / longest)
    lines = [_wrap_vis(c, max(4, int(slot * 9.0 / size)))[:4] for c in cats]
    ax.set_xticks(range(n))
    ax.set_xticklabels(["\n".join(x) for x in lines], fontsize=size,
                       rotation=0, ha="center")


def _vis_len(s: str) -> float:
    """視覺寬度：CJK 與全形標點算兩格，拉丁字元算一格。用來判斷頁尾會不會壓到品牌字。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


FOOT_W = 120          # 頁尾單行可容納的視覺寬度（x 0.075→0.925、fontsize 8 實測值）
# 同一條線（x 0.075→0.925）在不同字級下的視覺容量。**斷行機制 2026-08-08 就寫好了，
# 但只用在頁尾** —— 標題、副標與類別標籤各自沿用「單行 fig.text，超出就被裁掉」，
# 而被裁掉不留任何痕跡。2026-08-22 三張圖同時撞上：副標右緣截斷、
# 七個中文類別標籤糊成一團。**同一個缺陷三個位置，只修了一個。**
TITLE_W = 66          # fontsize 14.5
SUB_W = 96            # fontsize 10
TICK_W = 107          # fontsize 9，整個繪圖區
FOOT_MAX_LINES = 3    # 頁尾總行數上限，再多會吃掉圖面


def _wrap_vis(s: str, width: int = FOOT_W) -> list:
    """依視覺寬度斷行。中文沒有空白可斷，所以逐字元累加而不是用 textwrap。

    **為什麼需要這個**：頁尾原本是 `fig.text()` 單行輸出，超出圖框就被裁掉，
    而且不留任何痕跡。2026-08-08 實測抓到——`data/2026-08-05.json` 有一筆
    `note` 視覺寬 224，等於在已發布的 PNG 上被砍掉快一半，
    **而那些 PNG 正是 House View 月報直接取用的檔案**。
    """
    out, cur, w = [], "", 0
    for ch in s:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > width and cur:
            # **中文逐字斷沒問題，拉丁字母斷在詞中間會變成另一個字。**
            # 2026-08-22 副標把 `Fund Only` 斷成 `Fu / nd Only` ——
            # 回看最近的空白，找得到就在那裡斷，找不到才硬切。
            cut = cur.rfind(" ")
            if cut > len(cur) - 14 and cut > 0:
                out.append(cur[:cut])
                cur = cur[cut + 1:]
                w = sum(2 if ord(c) > 0x2E80 else 1 for c in cur)
            else:
                out.append(cur); cur, w = "", 0
        cur += ch; w += cw
    if cur:
        out.append(cur)
    return out or [""]


def _d(s):
    return dt.date.fromisoformat(s)

def _fmt(f):
    return FuncFormatter(lambda v, p: f.format(v))

# ---------------------------------------------------------------- PNG / SVG
NEW_KINDS = ("waterfall", "grouped_bar", "stacked_bar", "pct_stacked_bar",
             "range_area", "heatmap", "gauge")

# 有真實日期 x 軸的圖型 —— **只有這些能標 marker**。
# 其餘新圖型（waterfall、grouped_bar、stacked_bar、heatmap、gauge）的 x 軸是類別，
# 「在某個日期畫一條垂直線」在它們身上沒有意義。2026-08-11 那期圖 2（range_area）
# 寫了兩個 marker、檢查通過、兩軌都沒畫出來——**規則要求標記，實作卻默默丟掉**，
# 正是 brief §4 歷史縱深最怕的那種半殘。舊 check_day 已據此擋下（現為 `checks/chart.py` 的 `chart.series_wellformed`）無日期軸圖型的 marker。
DATE_AXIS_KINDS = ("timeseries", "range_area")
LINE_KINDS = ("timeseries",)     # 「非折線」的判定基準，檢查腳本用它守門


def _heat_color(v: float, lo: float, hi: float, diverge: bool):
    """熱力圖配色。**發散型（含正負）用藍↔紅、中點灰；單向用單一紅色斜坡。**

    這是唯一允許離開四角色制的地方——熱力圖的顏色編碼的是「量值大小」，
    不是「在論證裡的角色」，用四個離散角色表達連續量會讀不出來。
    """
    def mix(c1, c2, t):
        f = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
        a, b = f(c1), f(c2)
        return "#%02X%02X%02X" % tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))
    if diverge:
        m = max(abs(lo), abs(hi)) or 1.0
        t = v / m
        return mix("#F0EFEC", REF, min(1.0, -t)) if t < 0 else mix("#F0EFEC", ACCENT, min(1.0, t))
    t = 0.0 if hi == lo else (v - lo) / (hi - lo)
    return mix("#FFFFFF", ACCENT, t)


def _draw_waterfall(ch: Chart, ax):
    """瀑布圖：拆解一個變化是誰貢獻的。

    **配色刻意不用紅綠。** 增減方向已經由長條的位置與資料標籤表達；
    紅色保留給最後那根合計（`takeaway` 講的就是它）。增用對照藍、減用背景灰，
    同色系兩個深淺——這與第 4 節「正負值不分色、紅只給主角」是一致的。
    """
    cats, vals = list(ch.cats), list(ch.vals)
    if ch.total_label:
        cats, vals = cats + [ch.total_label], vals + [None]      # None＝合計欄
    run = 0.0
    for i, (c, v) in enumerate(zip(cats, vals)):
        if v is None:                                            # 合計欄由 0 畫到 run
            ax.bar(i, run, bottom=0, color=ACCENT, width=0.62, linewidth=0)
            top, lab = run, run
        else:
            ax.bar(i, v, bottom=run, color=(REF if v >= 0 else DIM), width=0.62, linewidth=0)
            top, lab = run + v, v
            if i < len(cats) - 1:                                # 銜接線
                ax.plot([i + 0.31, i + 0.69], [top, top], color=RULE, lw=0.8, zorder=1)
            run = top
        off = 6 if lab >= 0 else -14
        ax.annotate(ch.y_fmt.format(lab), (i, top), textcoords="offset points",
                    xytext=(0, off), ha="center", fontsize=8.5,
                    color=(ACCENT if v is None else MUTED),
                    fontweight=("bold" if v is None else "normal"))
    _fit_ticks(ax, cats)
    ax.axhline(0, color=RULE, lw=0.9)
    ax.grid(axis="y")


def _draw_grouped_bar(ch: Chart, ax):
    """分組柱形圖：同一組對象在兩個以上口徑下的對比。"""
    g = ch.groups
    n, m = len(ch.cats), len(g)
    w = 0.8 / max(m, 1)
    for j, grp in enumerate(g):
        xs = [i - 0.4 + w * (j + 0.5) for i in range(n)]
        ax.bar(xs, grp["values"], width=w * 0.9,
               color=grp.get("color") or PALETTE[j % len(PALETTE)],
               label=grp["name"], linewidth=0)
    _fit_ticks(ax, ch.cats)
    ax.axhline(0, color=RULE, lw=0.9)
    ax.grid(axis="y")


def _draw_stacked_bar(ch: Chart, ax, pct: bool = False):
    """堆積柱形圖：組成隨時間怎麼變。`pct=True` 為百分比堆積。

    **最多四個分項**——第五個會繞回主角紅，一張圖出現兩個主角。
    分項超過四個就把小的併成「其他」，那也是比較好讀的圖。
    """
    g = ch.groups
    n = len(ch.cats)
    cols = [list(x) for x in zip(*[grp["values"] for grp in g])] if g else []
    if pct and any(min(c) < 0 < max(c) for c in cols):
        raise ValueError("百分比堆積不能用在正負混合的資料上——分母沒有意義。改用一般堆積。")
    tot = [sum(abs(x) for x in c) or 1.0 for c in cols]
    # **正負要各自堆疊。** 統一累加會把正值疊進負值那一側，
    # 而 ECharts 預設是分開的——那就是兩軌各說各話。2026-08-09 目視驗收抓到。
    pos = [0.0] * n
    neg = [0.0] * n
    for j, grp in enumerate(g):
        v = [(grp["values"][i] / tot[i] * 100 if pct else grp["values"][i]) for i in range(n)]
        bot = [pos[i] if v[i] >= 0 else neg[i] for i in range(n)]
        ax.bar(range(n), v, bottom=bot, width=0.62,
               color=grp.get("color") or PALETTE[j % len(PALETTE)],
               label=grp["name"], linewidth=0)
        for i in range(n):
            if v[i] >= 0:
                pos[i] += v[i]
            else:
                neg[i] += v[i]
    _fit_ticks(ax, ch.cats)
    ax.axhline(0, color=RULE, lw=0.9)
    ax.grid(axis="y")


def _draw_markers(ch: Chart, ax):
    """在日期軸上標歷史錨點。**timeseries 與 range_area 共用同一份實作**——
    原本只寫在 timeseries 分支裡，range_area 就靜默漏掉了。"""
    for m in ch.markers:
        ax.axvline(_d(m.date), color=m.color, lw=0.9, ls=":", zorder=0)
        ax.annotate(m.label, (_d(m.date), 1.005), xycoords=("data", "axes fraction"),
                    fontsize=8, color=m.color, rotation=0, ha="center")


def _draw_range_area(ch: Chart, ax):
    """範圍面積圖：現在落在歷史區間的哪裡。band 是背景，線才是主角。"""
    xs = [_d(b[0]) for b in ch.band]
    lo = [b[1] for b in ch.band]; hi = [b[2] for b in ch.band]
    ax.fill_between(xs, lo, hi, color=DIM, alpha=0.35, linewidth=0,
                    label=ch.band_label or None)
    for i, s in enumerate(ch.series):
        ax.plot([_d(x) for x in s.dates], s.values, lw=s.width,
                color=s.color or PALETTE[i % len(PALETTE)], label=s.name)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
    ax.yaxis.set_major_formatter(_fmt(ch.y_fmt))
    ax.grid(axis="y")


def _draw_heatmap(ch: Chart, ax):
    """熱力圖：一整面的關係，不是兩兩比較。"""
    m = ch.matrix
    flat = [v for row in m for v in row if v is not None]
    lo, hi = min(flat), max(flat)
    div = lo < 0 < hi
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            if v is None:
                continue
            ax.add_patch(Rectangle((c, len(m) - 1 - r), 1, 1,
                                       facecolor=_heat_color(v, lo, hi, div),
                                       edgecolor="white", linewidth=1.4))
            # 文字色看「底色多深」，不是「值多大」。
            # 發散型的兩端都是深色——原本用 (v-lo) 判斷，藍色那端就會變成深字壓深底。
            depth = (abs(v) / max(abs(lo), abs(hi))) if div else (
                0.0 if hi == lo else (v - lo) / (hi - lo))
            ax.text(c + .5, len(m) - 1 - r + .5, ch.y_fmt.format(v),
                    ha="center", va="center", fontsize=8.5,
                    color=("white" if depth > 0.55 else INK))
    ax.set_xlim(0, len(ch.cats)); ax.set_ylim(0, len(m))
    ax.set_xticks([i + .5 for i in range(len(ch.cats))])
    _fit_ticks(ax, ch.cats)
    ax.set_yticks([len(m) - 1 - i + .5 for i in range(len(ch.rows))])
    ax.set_yticklabels(ch.rows, fontsize=9)
    # **左邊界要為列標籤讓位。** render_static 的 left=0.075 是給 y 軸刻度數字用的，
    # 熱力圖的 y 軸放的是中文列名（「費城半導體」＝五個全形字），2026-08-13 首次使用
    # 時「南韓 KOSPI」「費城半導體」都被切掉左半邊——PNG 是 House View 直接取用的檔案，
    # 所以那是實際流出去的缺陷。互動軌的 grid.left 早就設了 92，只有靜態軌沒跟上。
    ax.figure.subplots_adjust(left=0.155)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)


def _draw_gauge(ch: Chart, ax):
    """量表：單一數字距離門檻多遠。用半圓弧，不用圓餅。"""
    g = ch.gauge
    lo, hi, val = g.get("lo", 0.0), g.get("hi", 100.0), g["value"]
    frac = 0.0 if hi == lo else max(0.0, min(1.0, (val - lo) / (hi - lo)))
    for a0, a1, col, lw in ((180, 0, GRID, 26), (180, 180 - 180 * frac, ACCENT, 26)):
        ax.add_patch(Wedge((0, 0), 1.0, min(a0, a1), max(a0, a1),
                           width=0.26, facecolor=col, linewidth=0))
    if g.get("ref") is not None:                       # 參考線（門檻／中位數）
        rf = max(0.0, min(1.0, (g["ref"] - lo) / (hi - lo))) if hi != lo else 0
        a = math.radians(180 - 180 * rf)
        ax.plot([math.cos(a) * .72, math.cos(a) * 1.02], [math.sin(a) * .72, math.sin(a) * 1.02],
                color=INK, lw=1.6, zorder=6)
        ax.text(math.cos(a) * 1.12, math.sin(a) * 1.12, g.get("ref_label", ""),
                ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.text(0, 0.06, ch.y_fmt.format(val), ha="center", va="bottom",
            fontsize=30, color=ACCENT, fontweight="bold")
    ax.text(0, -0.16, ch.y_label, ha="center", fontsize=9.5, color=MUTED)
    ax.text(-1.0, -0.06, ch.y_fmt.format(lo), ha="center", fontsize=8.5, color=FAINT)
    ax.text(1.0, -0.06, ch.y_fmt.format(hi), ha="center", fontsize=8.5, color=FAINT)
    ax.set_xlim(-1.25, 1.25); ax.set_ylim(-0.3, 1.25)
    ax.set_aspect("equal"); ax.axis("off")


BRAND = "每日五圖 · Chart of the Day"


def render_static(ch: Chart, outdir: str, basename: str, brand: str = BRAND) -> dict:
    """`brand` 是右下角那行字。**它是出品方，不是繪圖引擎的一部分。**

    外資報告週摘也用這支繪圖，若沿用預設值，一張依券商報告重製的圖會掛上
    每日五圖的品牌 —— 圖被複製出去以後，看的人無從分辨那是誰的主張。
    給空字串就不畫。
    """
    apply_style()
    _label_slots.clear()
    fig, ax = plt.subplots(figsize=(8.6, 4.9))
    # bottom 0.17 是單行標籤的值。多行類別標籤要更多空間，
    # 由 `_fit_ticks` 之後重算 —— 見下方 `fig.subplots_adjust(bottom=…)`。
    fig.subplots_adjust(left=0.075, right=0.925, top=0.80, bottom=0.17)
    ax2 = None

    if ch.kind in NEW_KINDS:
        {"waterfall": _draw_waterfall, "grouped_bar": _draw_grouped_bar,
         "stacked_bar": lambda c, a: _draw_stacked_bar(c, a, False),
         "pct_stacked_bar": lambda c, a: _draw_stacked_bar(c, a, True),
         "range_area": _draw_range_area, "heatmap": _draw_heatmap,
         "gauge": _draw_gauge}[ch.kind](ch, ax)
        if ch.kind not in ("gauge", "heatmap"):
            ax.set_ylabel(ch.y_label, fontsize=9)
        if ch.zero_line and ch.kind not in ("gauge", "heatmap"):
            ax.axhline(0, color=RULE, lw=0.9)
        if ch.kind in DATE_AXIS_KINDS:
            _draw_markers(ch, ax)
    elif ch.kind == "scatter":
        xs = [p[0] for p in ch.pts]; ys = [p[1] for p in ch.pts]
        ax.scatter(xs, ys, s=13, c=FAINT, alpha=0.55, linewidths=0)
        ax.axhline(0, color=RULE, lw=0.9); ax.axvline(0, color=RULE, lw=0.9)
        offs = [(11, 9), (11, -15), (-14, 12), (-14, -18)]   # 交錯避免標籤互壓
        for k, (x, y, lab) in enumerate(ch.hi_pts):
            ax.scatter([x], [y], s=66, c=ACCENT, zorder=5, linewidths=0)
            dx, dy = offs[k % len(offs)]
            ax.annotate(lab, (x, y), textcoords="offset points", xytext=(dx, dy),
                        fontsize=9, color=ACCENT, fontweight="bold",
                        ha="left" if dx > 0 else "right",
                        arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.7,
                                        shrinkA=0, shrinkB=4))
        ax.set_xlabel(ch.x_label, fontsize=9)
        ax.set_ylabel(ch.y_label, fontsize=9)
        ax.grid(True, axis="both")
    else:
        # 雙軸圖不用面積填色：填到 y=0 會把兩條線壓在上緣，也會誤導比例
        dual = any(s.axis == "right" for s in ch.series)
        for i, s in enumerate(ch.series):
            col = s.color or PALETTE[i % len(PALETTE)]
            if dual and s.style == "area":
                s = ck_replace(s, style="line")
            x = [_d(d) for d in s.dates]
            tgt = ax
            if s.axis == "right":
                if ax2 is None:
                    ax2 = ax.twinx(); ax2.grid(False)
                    ax2.spines["right"].set_visible(True)
                    ax2.spines["right"].set_color(RULE)
                tgt = ax2
            if s.style == "area":
                tgt.fill_between(x, s.values, color=col, alpha=0.13, linewidth=0)
                tgt.plot(x, s.values, color=col, lw=s.width,
                         ls="--" if s.dash else "-", label=s.name)
            elif s.style == "bar":
                # 長條寬度要跟著資料頻率走。原本寫死 1.0（＝一天），畫日頻沒問題，
                # 但月頻資料的點距是 30 天，1 天寬的柱子會細成一根針——
                # 2026-08-09 做非農月增圖時實測到。取相鄰日期中位距的 0.8 倍。
                gaps = sorted((x[k + 1] - x[k]).days for k in range(len(x) - 1)) if len(x) > 1 else [1]
                tgt.bar(x, s.values, color=col, width=max(1, gaps[len(gaps) // 2]) * 0.8,
                        linewidth=0, label=s.name)
            else:
                tgt.plot(x, s.values, color=col, lw=s.width,
                         ls="--" if s.dash else "-", label=s.name)
            # 末值標籤（同軸多條線時上下錯開，避免互壓）
            if s.style != "bar" and s.values:
                last = next((v for v in reversed(s.values) if v is not None), None)
                if last is not None:
                    # 以「軸內相對位置」判斷碰撞——雙軸時兩條線的絕對值不可比。
                    # **範圍要取同一軸上所有序列的聯集，不是這一條自己的 min/max。**
                    # 用自己的範圍等於各自歸一化，兩條末值幾乎相同的線會算出不同的
                    # frac 而被判為不碰撞：2026-08-13 memory-vs-sox 的美光 319.29 與
                    # 希捷 318.90 就是這樣疊印成一團（frac 0.66 對 0.73，差 0.07 剛好
                    # 大於門檻 0.06）。同軸序列本來就共用刻度，範圍當然要一起算。
                    axis_key = s.axis or "left"
                    same = [t for t in ch.series if (t.axis or "left") == axis_key
                            and t.style != "bar"]
                    pool = [v for t in same for v in t.values if v is not None]
                    lo_, hi_ = (min(pool), max(pool)) if pool else (0.0, 1.0)
                    frac = (last - lo_) / (hi_ - lo_) if hi_ > lo_ else 0.5
                    used = _label_slots.setdefault(axis_key, [])
                    dy = -3
                    for prev in used:
                        if abs(prev - frac) < 0.06:
                            dy += 12
                    used.append(frac)
                    tgt.annotate(f"{last:,.2f}".rstrip("0").rstrip("."),
                                 (x[-1], last), textcoords="offset points",
                                 xytext=(5, dy), fontsize=8.5, color=col,
                                 fontweight="bold")
        if ch.zero_line:
            ax.axhline(0, color=RULE, lw=1.0)
        _draw_markers(ch, ax)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
        ax.yaxis.set_major_formatter(_fmt(ch.y_fmt))
        if ax2 is not None:
            ax2.yaxis.set_major_formatter(_fmt(ch.y2_fmt))
            ax2.tick_params(colors=MUTED, labelsize=9)

        # y 軸依資料範圍留白，不強制從 0 起（除非資料本身跨零）
        def _pad(axis, sers):
            vals = [v for s in sers for v in s.values if v is not None]
            if not vals:
                return
            lo, hi = min(vals), max(vals)
            if lo == hi:
                return
            if ch.y_log and lo > 0:
                axis.set_yscale("log")
                axis.set_ylim(lo * 0.88, hi * 1.18)
                axis.yaxis.set_major_formatter(_fmt(ch.y_fmt))
                axis.yaxis.set_minor_formatter(_fmt(ch.y_fmt))
                axis.tick_params(axis="y", which="minor", labelsize=7.5, colors=FAINT)
                return
            m = (hi - lo) * 0.10
            axis.set_ylim(min(lo - m, 0) if lo < 0 else lo - m, hi + m * 1.6)
        _pad(ax, [s for s in ch.series if s.axis != "right"])
        if ax2 is not None:
            _pad(ax2, [s for s in ch.series if s.axis == "right"])

    ax.grid(axis="x", visible=(ch.kind == "scatter"))
    ax.tick_params(length=0)

    # 圖例的標籤要在排標題區之前就知道 —— **圖面要讓多少位，取決於有沒有圖例**。
    labels_hint = ax.get_legend_handles_labels()[1] + (
        ax2.get_legend_handles_labels()[1] if ax2 is not None else [])
    # 類別軸圖型：頂端留 12% 餘裕，否則最高那根會鑽進圖例底下
    # （2026-08-22 亞太那張的第一根就被切掉了，而圖看起來仍然完整）。
    if ch.kind in ("grouped_bar", "stacked_bar", "waterfall", "pct_stacked_bar"):
        # **兩端都要留**：瀑布圖的累計路徑可以跌到任何一根長條的值以下，
        # 2026-08-22 泰國那張最低點在 −2.7 而 y 軸底是 −2.4，**最後一段被切掉**。
        # 用 `margins` 而不是自己算 —— 它看的是實際畫出來的東西，不是我以為畫了什麼。
        # **從實際畫出來的東西算，不是從我以為畫了什麼算。**
        # `margins()` 要在 autoscale 之後才生效，順序錯了就完全沒作用 ——
        # 這一格 2026-08-22 改了兩次，第一次改完圖看起來完全一樣。
        ax.relim()
        lo_, hi_ = ax.dataLim.y0, ax.dataLim.y1
        span = (hi_ - lo_) or 1.0
        # 資料標籤畫在長條的外側（正值在上、負值在下），所以兩端都要含它的高度。
        ax.set_ylim(lo_ - span * 0.16 if lo_ < 0 else 0, hi_ + span * 0.16)

    # 標題區 —— **標題與副標一樣會被裁掉，而且不留痕跡**（見 TITLE_W 的註解）。
    # 斷行之後往下長，圖面跟著讓位；讓位的量由行數決定，不是猜的。
    tl = _wrap_vis(ch.title, TITLE_W)[:2]
    sl = _wrap_vis(ch.subtitle, SUB_W)[:3] if ch.subtitle else []
    y = 0.955
    for i, line in enumerate(tl):
        fig.text(0.075, y - i * 0.052, line, fontsize=14.5, fontweight="bold",
                 color=INK, va="top")
    y -= len(tl) * 0.052 + 0.012
    for i, line in enumerate(sl):
        fig.text(0.075, y - i * 0.036, line, fontsize=10, color=MUTED, va="top")
    y -= len(sl) * 0.036
    # 圖例畫在圖面上緣之上，所以圖面頂端要留在標題區底下再減圖例的高度。
    top = min(0.82, y - (0.055 if len(labels_hint) > 1 else 0.015))
    fig.subplots_adjust(top=max(0.60, top))
    # 多行類別標籤要往下長，不讓位就會壓到頁尾。
    nl = max((str(t.get_text()).count("\n") for t in ax.get_xticklabels()), default=0)
    if nl:
        fig.subplots_adjust(bottom=min(0.42, 0.17 + nl * 0.035))
    # 圖例
    handles, labels = ax.get_legend_handles_labels()
    if ax2 is not None:
        h2, l2 = ax2.get_legend_handles_labels(); handles += h2; labels += l2
    if len(labels) > 1:
        ax.legend(handles, labels, loc="upper left", frameon=False,
                  fontsize=9, ncol=min(len(labels), 4),
                  bbox_to_anchor=(0, 1.02), handlelength=1.6)
    # 頁尾：來源與註記優先；太長時續排並讓出品牌位置，絕不互壓、**也絕不靜默裁字**。
    foot = ch.source if not ch.note else f"{ch.source}    |    {ch.note}"
    # **實際折了幾行只有這裡知道。** 檢查那一側是用固定視覺寬估的。
    # 2026-08-22 拿當期五張圖對過：檢查的估算（逐欄無條件進位）與這裡量到的
    # 3／3／2／3／3 **完全一致** —— 估算今天沒有失準。
    # 那為什麼還要把量測帶回去？因為估算**照不到截斷**：超過 FOOT_MAX_LINES 時
    # 這裡會切字並補刪節號，而估算只會回一個大於上限的數字，說不出「已經被切了」。
    # 同一天的執行報告曾寫「估算比排版引擎樂觀、差一行」，那是報告作者另寫的一套
    # 估算法算錯，不是這條檢查 —— **更正留痕，見 CHANGELOG 2026-08-22。**
    foot_lines, foot_cut = 1, False
    if _vis_len(foot) > 78:
        lines = _wrap_vis(ch.source) + (_wrap_vis(ch.note) if ch.note else [])
        foot_lines = len(lines)                      # **截斷前**的行數才是要守的那個量
        foot_cut = len(lines) > FOOT_MAX_LINES
        if len(lines) > FOOT_MAX_LINES:
            # 超過上限就截斷，但**留一個看得見的刪節號**——
            # 靜默裁字會讓人以為文字本來就那麼短，是這次要修掉的正是那個行為。
            lines = lines[:FOOT_MAX_LINES]
            lines[-1] = lines[-1][:-1] + "…"
        for k, line in enumerate(reversed(lines)):      # 由下往上排，最後一行貼齊底部
            fig.text(0.075, 0.012 + k * 0.024, line, fontsize=8, color=FAINT, va="bottom")
    else:
        fig.text(0.075, 0.035, foot, fontsize=8, color=FAINT, va="bottom")
        if brand:
            fig.text(0.925, 0.035, brand, fontsize=8,
                     color=FAINT, va="bottom", ha="right")

    os.makedirs(outdir, exist_ok=True)
    png = os.path.join(outdir, basename + ".png")
    svg = os.path.join(outdir, basename + ".svg")
    fig.savefig(png, dpi=200)
    fig.savefig(svg, metadata={"Date": None})      # 不寫入產生時間，同上理由
    plt.close(fig)
    return {"png": png, "svg": svg,
            "footer_lines": foot_lines, "footer_truncated": foot_cut}

# ---------------------------------------------------------------- ECharts
def qa_series(ch: Chart, z: float = 5.0) -> list:
    """資料品質檢查：抓單日跳動異常大的點。

    期貨連續序列的轉倉、來源端的錯價、單位變更，都會表現成一根突兀的單日跳動。
    這些點如果沒被抓出來，會直接變成圖上的假訊號。回傳待人工覆核的清單。

    門檻為何是 5σ 而不是 6σ（2026-08-05 實測後調整）：
        6σ 漏掉了 2026-01-30 黃金單日 −11.37%（z=−5.59）。一根 11% 的單日棒子沒被
        任何機制看一眼，正是這個檢查該擋下來的東西，所以門檻本身失職。
        改 5σ 後同一份資料由 2 筆增為 7 筆，經下述連續日合併後為 5 筆。多出來的
        全是已知的真實事件（2024-08-02、2025-04-03/04、2025-05-12），依
        AGENT_BRIEF 第 3.4 節屬「保留並可在判讀中引用」。
        **多出來的不是雜訊，是本來就該被讀到的東西。**

    連續日合併：同一序列相鄰交易日的旗標會併成一筆並記 date_end。
        2025-04-03 與 04-04 是同一次關稅衝擊，算成兩筆只會讓 about.run 的處置
        說明變成流水帳，讀的人反而抓不到重點。

    衍生序列（`Series.derived=True`）的旗標會標上 `"derived": True`：
        滾動波動率、移動平均這類量的單日跳動來自「窗口進出」——某一天的極端值
        滾出 60 日窗口，指標就跳一階。**那不是市場事件、不是轉倉、也不是錯價，
        是檢查方法與衍生序列不相容。** 2026-08-06 那期 18 筆旗標裡有 13 筆是
        這一種（黃金 ETF 60 日波動率），全部要求逐筆說明只會逼出罐頭文字。
        標記後由 AGENT_BRIEF 第 3.4 節第四類統一處置：整條序列說明一次即可。
    """
    flags = []
    for s in ch.series:
        v = [x for x in s.values if x is not None]
        if len(v) < 30:
            continue
        # 穿越零的序列（買賣超、淨流量這類「流量」）不能用百分比變動：
        # 分母趨近 0 時比值會爆炸。2026-08-11 那期外資買賣超在 2026-07-01 由
        # −0.6 億轉為 +38 億，算出來是 **−6449%**，序列本身完全正確。
        # 這種誤報每個月都會來好幾次，而每天人工判讀一次「這又是分母失真」
        # 只會磨掉對紅字的敏感度——**會固定誤報的檢查，比沒有檢查更糟**。
        # 對這類序列改用「絕對變動」的 z 分數：一樣抓得到真正突兀的跳動，
        # 而且量綱一致。`pct` 欄位在這種情況下改記絕對變動，並標 `abs_chg`。
        flow = min(v) < 0 < max(v)
        if flow:
            rets = [(v[i] - v[i - 1]) for i in range(1, len(v))]
        else:
            rets = [(v[i] / v[i - 1] - 1) for i in range(1, len(v)) if v[i - 1]]
        if not rets:
            continue
        mu = sum(rets) / len(rets)
        sd = (sum((r - mu) ** 2 for r in rets) / len(rets)) ** 0.5
        if sd == 0:
            continue
        hits = [i for i, r in enumerate(rets, start=1) if abs(r - mu) > z * sd]
        run = []                      # 收集連續索引，遇到斷點就結算成一筆
        for idx in hits + [None]:
            if run and (idx is None or idx != run[-1] + 1):
                peak = max(run, key=lambda i: abs(rets[i - 1] - mu))
                r = rets[peak - 1]
                f = {"chart": ch.slug, "series": s.name,
                     "date": s.dates[run[0]] if run[0] < len(s.dates) else "?",
                     "pct": round(r if flow else r * 100, 2),
                     "z": round((r - mu) / sd, 1)}
                if flow:
                    f["abs_chg"] = True
                if s.derived:
                    f["derived"] = True
                if len(run) > 1:      # 只有跨日事件才寫 date_end 與 days
                    f["date_end"] = s.dates[run[-1]] if run[-1] < len(s.dates) else "?"
                    f["days"] = len(run)
                flags.append(f)
                run = []
            if idx is not None:
                run.append(idx)
    return flags


def _marker_markline(ch: Chart) -> dict:
    """marker 的 ECharts 表示。與 `_draw_markers` 是一組兩份。"""
    return {"silent": True, "symbol": "none",
            "lineStyle": {"color": FAINT, "type": "dotted"},
            "data": [{"xAxis": m.date, "label": {"formatter": m.label,
                      "color": FAINT, "fontSize": 10}} for m in ch.markers]}


def _echarts_new_kind(ch: Chart, base: dict) -> dict:
    """六種新圖型的互動軌。

    **與 `render_static` 是一組兩份，改一邊必須改另一邊**——這套系統是雙軌產出，
    2026-08-06 就因為 `echarts_option` 少實作了依日期對位，讓網頁上的線整條位移
    八個交易日而 PNG 正常。新圖型更容易發生這種事，因為兩邊的資料結構差很多。
    """
    cat = {"type": "category", "data": list(ch.cats), "axisLine": {"lineStyle": {"color": RULE}},
           "axisLabel": {"color": MUTED}}
    val = {"type": "value", "name": ch.y_label, "splitLine": {"lineStyle": {"color": GRID}},
           "axisLabel": {"color": MUTED}}

    if ch.kind == "waterfall":
        # ECharts 沒有瀑布型別，慣例是用一條透明的墊底堆疊出來。
        #
        # **但 ECharts 預設把正值與負值分開堆疊**（`stackStrategy: "samesign"`）。
        # 墊底是負的、可見長條是 abs()＝正的，兩者因此各走各的堆疊，
        # 每根都從 0 往上長——整座階梯消失、跌的日子看起來像漲的，而且不丟任何例外。
        # 2026-08-12 waterfall 首次上線即如此（PNG 正確）。`stackStrategy: "all"`
        # （ECharts ≥5.3.3，本站載 5.5.0）才會把正負一起累加。
        # 同一個「正負分開堆疊」的坑，`_draw_stacked_bar` 的註解 2026-08-09 就記過一次。
        pad, bar, run = [], [], 0.0
        for v in ch.vals:
            pad.append(round(min(run, run + v), 6)); bar.append(abs(v)); run += v
        names = list(ch.cats)
        cols = [(REF if v >= 0 else DIM) for v in ch.vals]
        # 資料標籤要顯示原始的帶號值——可見長條的高度是 abs()，直接印會讓 −6.35 變成 6.35
        labs = [{"formatter": ch.y_fmt.format(v), "color": MUTED} for v in ch.vals]
        if ch.total_label:
            names.append(ch.total_label); pad.append(0); bar.append(run); cols.append(ACCENT)
            labs.append({"formatter": ch.y_fmt.format(run), "color": ACCENT,
                         "fontWeight": "bold"})
        base.update({"xAxis": {**cat, "data": names}, "yAxis": val, "series": [
            {"type": "bar", "stack": "w", "stackStrategy": "all", "silent": True,
             "itemStyle": {"opacity": 0}, "data": pad, "tooltip": {"show": False}},
            {"type": "bar", "stack": "w", "stackStrategy": "all", "barWidth": "62%",
             "name": ch.y_label,
             "data": [{"value": b, "itemStyle": {"color": c}, "label": lb}
                      for b, c, lb in zip(bar, cols, labs)],
             "label": {"show": True, "position": "top", "color": MUTED, "fontSize": 10}}]})
        return base

    if ch.kind in ("grouped_bar", "stacked_bar", "pct_stacked_bar"):
        pct = ch.kind == "pct_stacked_bar"
        stack = None if ch.kind == "grouped_bar" else "s"
        tot = [sum(g["values"][i] for g in ch.groups) or 1.0 for i in range(len(ch.cats))]
        # **`barWidth` 是「每一條」的寬度，不是「一整組」的寬度。**
        # 堆疊圖每條都疊在同一個位置，62% 就是整組 62%，與靜態軌的 width=0.62 相符；
        # 但分組圖是並排的，兩條各 62% 會讓一組佔掉類別帶的 143%（還要加 barGap），
        # 溢出的部分被 ECharts 往旁邊推，柱子就與 x 軸標籤對不上——
        # 2026-08-12 grouped_bar 首次上線即如此（PNG 正確、網頁位移）。
        # 分組圖改用 `barCategoryGap` 指定「一整組佔類別帶多少」，寬度交給 ECharts 均分，
        # 對齊靜態軌的 0.8／組、組內 0.9 佔比。
        width = {"barCategoryGap": "20%", "barGap": "10%"} if stack is None \
            else {"barWidth": "62%"}
        base.update({"xAxis": cat, "yAxis": {**val, **({"max": 100} if pct else {})},
                     "legend": {"top": 2, "textStyle": {"color": MUTED}},
                     "series": [
                         {"type": "bar", "name": g["name"], "stack": stack, **width,
                          "itemStyle": {"color": g.get("color") or PALETTE[j % len(PALETTE)]},
                          "data": [(g["values"][i] / tot[i] * 100 if pct else g["values"][i])
                                   for i in range(len(ch.cats))]}
                         for j, g in enumerate(ch.groups)]})
        return base

    if ch.kind == "range_area":
        dates = [b[0] for b in ch.band]
        lo = [b[1] for b in ch.band]
        rng = [b[2] - b[1] for b in ch.band]
        by = {s.name: dict(zip(s.dates, s.values)) for s in ch.series}
        base.update({"xAxis": {**cat, "data": dates, "boundaryGap": False}, "yAxis": val,
                     "legend": {"top": 2, "textStyle": {"color": MUTED}},
                     "series": [
                         {"type": "line", "stack": "band", "silent": True, "symbol": "none",
                          "lineStyle": {"opacity": 0}, "data": lo, "tooltip": {"show": False}},
                         {"type": "line", "stack": "band", "silent": True, "symbol": "none",
                          "name": ch.band_label or "區間", "lineStyle": {"opacity": 0},
                          "areaStyle": {"color": DIM, "opacity": 0.35}, "data": rng}] + [
                         {"type": "line", "name": s.name, "showSymbol": False,
                          "connectNulls": True,
                          "lineStyle": {"width": s.width,
                                        "color": s.color or PALETTE[i % len(PALETTE)]},
                          "itemStyle": {"color": s.color or PALETTE[i % len(PALETTE)]},
                          "data": [by[s.name].get(d) for d in dates]}
                         for i, s in enumerate(ch.series)]})
        if ch.markers and ch.series:
            # 掛在主線上，不掛在墊底的兩條堆疊——那兩條是 silent 的，markLine 會被吃掉
            base["series"][-1]["markLine"] = _marker_markline(ch)
        return base

    if ch.kind == "heatmap":
        flat = [v for row in ch.matrix for v in row if v is not None]
        lo, hi = min(flat), max(flat)
        div = lo < 0 < hi
        data = [[c, len(ch.matrix) - 1 - r, v]
                for r, row in enumerate(ch.matrix) for c, v in enumerate(row) if v is not None]
        base.update({
            "tooltip": {"trigger": "item"},
            "grid": {"left": 92, "right": 40, "top": 34, "bottom": 46},
            "xAxis": {**cat, "splitArea": {"show": False}},
            "yAxis": {"type": "category", "data": list(reversed(ch.rows)),
                      "axisLine": {"lineStyle": {"color": RULE}},
                      "axisLabel": {"color": MUTED}},
            "series": [{"type": "heatmap", "data": [
                {"value": d, "itemStyle": {"color": _heat_color(d[2], lo, hi, div)},
                 # 文字色與靜態軌同一條規則：看底色多深，不是看值多大
                 "label": {"color": ("#FFFFFF" if (
                     (abs(d[2]) / max(abs(lo), abs(hi))) if div else
                     (0.0 if hi == lo else (d[2] - lo) / (hi - lo))) > 0.55 else INK)}}
                for d in data],
                "label": {"show": True, "fontSize": 10, "formatter": "{@[2]}"},
                "itemStyle": {"borderColor": "#FFFFFF", "borderWidth": 2}}]})
        return base

    # gauge
    #
    # **參考線不能用 `markLine`。** gauge 不掛在直角座標系上，`{"yAxis": ref}` 會讓
    # ECharts 去問一個不存在的軸，丟 `Cannot read properties of undefined (reading 'getAxis')`；
    # 而 index.html 只有一層 `boot().catch`，**一張圖丟例外就整頁只剩「載入失敗」**。
    # 2026-08-12 首次使用 gauge 當天就撞上——**新圖型的互動軌沒有被任何檢查跑過**，
    # 檢查程式看的是 JSON 欄位齊不齊，不會把 option 餵進 ECharts。
    #
    # 改法：參考刻度用第二條 gauge 疊上去，只在 ref 的角度留一小段深色 axisLine，
    # 其餘透明。角度由 ECharts 自己換算，不必手算 pointer 長度；疊在主序列之後
    # 所以不會被紅色 progress 蓋掉（靜態軌是靠 zorder=6 達到同一件事）。
    # ref_label 併進主序列的 name——gauge 的 title 是固定偏移、不跟著角度走，
    # 硬要貼在刻度旁邊會在 ref 靠近兩端時飛出圖外。
    g = ch.gauge
    base.pop("tooltip", None)
    base.pop("grid", None)
    lo, hi, ref = g.get("lo", 0.0), g.get("hi", 100.0), g.get("ref")
    name = ch.y_label
    marks = []
    if ref is not None and hi != lo:
        rf = max(0.0, min(1.0, (ref - lo) / (hi - lo)))
        w, clear = 0.005, "rgba(0,0,0,0)"
        marks = [{"type": "gauge", "startAngle": 180, "endAngle": 0, "radius": "92%",
                  "center": ["50%", "72%"], "min": lo, "max": hi, "silent": True, "z": 10,
                  "progress": {"show": False}, "pointer": {"show": False},
                  "axisTick": {"show": False}, "splitLine": {"show": False},
                  "axisLabel": {"show": False}, "detail": {"show": False},
                  "title": {"show": False},
                  "axisLine": {"lineStyle": {"width": 22, "color": [
                      [max(0.0, rf - w), clear], [min(1.0, rf + w), INK], [1, clear]]}},
                  "data": []}]
        if g.get("ref_label"):
            name = f'{ch.y_label}｜{g["ref_label"]}'
    base.update({"series": [{
        "type": "gauge", "startAngle": 180, "endAngle": 0, "radius": "92%",
        "center": ["50%", "72%"], "min": lo, "max": hi, "z": 1,
        "progress": {"show": True, "width": 22, "itemStyle": {"color": ACCENT}},
        "axisLine": {"lineStyle": {"width": 22, "color": [[1, GRID]]}},
        "pointer": {"show": False}, "axisTick": {"show": False},
        "splitLine": {"show": False},
        # splitNumber 預設 10，會沿著弧線印出十個刻度數字把圖蓋滿；
        # 靜態軌只標下緣與上緣兩個值，這裡對齊成同一種讀法。
        "splitNumber": 1,
        "axisLabel": {"color": FAINT, "fontSize": 10, "distance": -32,
                      "formatter": "{value}"},
        "title": {"show": True, "offsetCenter": [0, "26%"],
                  "color": MUTED, "fontSize": 12},
        "detail": {"valueAnimation": False, "offsetCenter": [0, "-8%"],
                   "color": ACCENT, "fontSize": 30, "fontWeight": "bold",
                   "formatter": ch.y_fmt.format(g["value"])},
        "data": [{"value": g["value"], "name": name}]}] + marks})
    return base


# 零線：靜態軌在 render_static() 用 axhline 畫。互動軌原本**只有 timeseries 那條路有**——
# 2026-08-20 對帳發現站上 7 張標了 zero_line 的圖裡，只有 1 張（唯一那張 timeseries）
# 的 option 有零線，grouped_bar 4 張、scatter 1 張、waterfall 1 張全部沒有。
#
# 這是「**改一半比沒改更難發現**」的教科書案例：當初測的那個案例剛好是 timeseries，
# 所以看起來修好了。抽成共用函式並讓三條出口都經過它，讓「哪一種圖型」不再是變因。
#
# gauge 與 heatmap 排除，與 render_static() 第 408 行的條件逐字相同——
# 那兩種沒有可言的零線。
def _apply_zero_line(ch: Chart, base: dict) -> dict:
    if not ch.zero_line or ch.kind in ("gauge", "heatmap"):
        return base
    if not base.get("series"):
        return base
    s0 = base["series"][0]
    ml = s0.get("markLine") or {"silent": True, "symbol": "none", "data": []}
    ml.setdefault("data", [])
    ml["data"] = list(ml["data"]) + [{
        "yAxis": 0, "lineStyle": {"color": RULE, "width": 1.0, "type": "solid"},
        "label": {"show": False},
    }]
    s0["markLine"] = ml
    return base


def echarts_option(ch: Chart) -> dict:
    """與 render_static 同源；前端直接 setOption。"""
    base = {
        "animation": False,
        "grid": {"left": 58, "right": 58, "top": 34, "bottom": 46},
        "tooltip": {"trigger": "axis" if ch.kind != "scatter" else "item",
                    "axisPointer": {"type": "line"}},
        "color": PALETTE,
        "textStyle": {"fontFamily": "'Noto Sans TC','PingFang TC',sans-serif"},
    }
    if ch.kind in NEW_KINDS:
        return _apply_zero_line(ch, _echarts_new_kind(ch, base))
    if ch.kind == "scatter":
        base.update({
            "xAxis": {"type": "value", "name": ch.x_label, "nameLocation": "middle",
                      "nameGap": 26, "splitLine": {"lineStyle": {"color": GRID}}},
            "yAxis": {"type": "value", "name": ch.y_label,
                      "splitLine": {"lineStyle": {"color": GRID}}},
            "series": [
                {"type": "scatter", "symbolSize": 6, "data": [list(p) for p in ch.pts],
                 "itemStyle": {"color": FAINT, "opacity": 0.55}, "name": "歷史交易日"},
                {"type": "scatter", "symbolSize": 13,
                 "data": [{"value": [p[0], p[1]], "name": p[2]} for p in ch.hi_pts],
                 "itemStyle": {"color": ACCENT}, "name": "同步上漲日",
                 "label": {"show": True, "formatter": "{b}", "position": "top",
                           "color": ACCENT, "fontWeight": "bold"}},
            ],
        })
        return _apply_zero_line(ch, base)

    # x 軸取所有序列日期的聯集，不是 series[0] 的日期。
    #
    # **ECharts 的 category 軸是按「位置」貼資料，不是按日期。** 原本用 series[0].dates
    # 當軸、每條序列直接丟 s.values，只要某條序列長度不同，整條線就會靜默位移——
    # 而且靜態軌（matplotlib 用真實日期畫）完全正確，所以兩軌會不一致，網頁錯、PNG 對。
    #
    # 2026-08-06 實測到的兩個實例：
    #   · 08-06 圖 2 的「2016–2025 中位數」只有 42 點、軸有 2,452 點，
    #     那條參考線被畫在最左邊 1.7% 的寬度裡，看起來像沒畫出來。
    #   · 08-05 圖 5 的「台股加權」有 140 點、軸有 146 點，末端被畫在 2026-07-24
    #     的位置（實際是 08-05），**整條位移八個交易日**——而那張圖的判讀正是在
    #     比較台股與費半的相對走勢。
    #
    # 取聯集並依日期補 None，再開 connectNulls，稀疏序列（例如常數參考線）
    # 就會連成一條完整的橫線，長度不同的序列也會各自落在正確的日期上。
    dates = sorted({d for s in ch.series for d in s.dates})
    ys = [{"type": "log" if ch.y_log else "value", "scale": True, "name": ch.y_label,
           "splitLine": {"lineStyle": {"color": GRID}},
           "axisLabel": {"color": MUTED}}]
    if any(s.axis == "right" for s in ch.series):
        ys.append({"type": "value", "scale": True, "name": ch.y2_label,
                   "splitLine": {"show": False}, "axisLabel": {"color": MUTED}})
    base.update({
        "legend": {"top": 2, "textStyle": {"color": MUTED}},
        "xAxis": {"type": "category", "data": dates, "boundaryGap": False,
                  "axisLabel": {"color": MUTED,
                                "formatter": "{value}"},
                  "axisLine": {"lineStyle": {"color": RULE}}},
        "yAxis": ys,
        "series": [],
    })
    for i, s in enumerate(ch.series):
        col = s.color or PALETTE[i % len(PALETTE)]
        # 依日期對位到聯集軸上，缺的補 None。**不要直接丟 s.values**——那是位置對應。
        by_date = dict(zip(s.dates, s.values))
        item = {
            "name": s.name, "type": "bar" if s.style == "bar" else "line",
            "showSymbol": False, "smooth": False,
            "connectNulls": True,       # 稀疏序列（常數參考線）要連成完整一條
            "yAxisIndex": 1 if s.axis == "right" else 0,
            "lineStyle": {"width": s.width, "type": "dashed" if s.dash else "solid"},
            "itemStyle": {"color": col},
            "data": [by_date.get(d) for d in dates],
        }
        if s.style == "area":
            item["areaStyle"] = {"opacity": 0.13}
        base["series"].append(item)
    if ch.markers and base["series"]:
        base["series"][0]["markLine"] = _marker_markline(ch)
    # 正負值不分色之後，零線是唯一區分正負的視覺元素——兩軌都要有，
    # 否則網頁上的讀者看不出正負的分界，而 PNG 上看得出來。
    return _apply_zero_line(ch, base)
