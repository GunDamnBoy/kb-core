#!/usr/bin/env python3
"""把一期 digest.json 排成給人讀的 Markdown。**這支會寫檔，但只寫 .md。**

用法：render.py <digest.json> [-o OUT.md]

## 這支不做的事

**它不產生任何內容。** 每一個字都是從 JSON 搬過來的 ——
精華、原句、圖說、字數、檔案連結都有各自的來源，這裡只負責排版。
一旦這裡開始「順一下文字」，digest.json 就不再是單一錨點，
而讀的人會以為自己讀的是撰寫者寫的東西。

因此 `assemble.py` 每次組完就順手叫這支：**衍生檔不留在手動重跑的路徑上**，
否則 JSON 改了、MD 沒改，兩份看起來都像對的。
"""
from __future__ import annotations
import argparse, base64, json, os, re, sys

TIER = {3000: "≤10 頁", 4000: "11–30 頁", 5000: ">30 頁"}


def demote(md, by=1):
    """精華內部用 `##` 起跳；報告本身是 `##`，不降階會把層級壓平。"""
    return re.sub(r"^(#{1,5})(?=\s)", lambda m: "#" * min(6, len(m.group(1)) + by),
                  md or "", flags=re.M)


def anchor(slug):
    return "report-" + slug


def title_of(r):
    """`title` 是檔名去副檔名 —— macOS 的檔名放不了冒號，券商就用 `_` 代替，
    於是標題讀起來像 `Top of Mind_ Assessing a less transparent Fed`。

    **這一層只改顯示，不回寫 digest.json。** 冒號是猜的，猜錯了要能一眼看出來
    是排版的問題；寫回資料庫就變成無法分辨的既成事實。
    """
    t = re.sub(r"_\s+", "：", (r.get("title") or "?")).strip()
    return re.sub(r"_+$", "？", t)          # 結尾的 `_` 是被替換掉的問號


def render(d, charts_dir="charts"):
    L = []
    w = d.get("week", "?")
    rng = d.get("range") or ["?", "?"]
    tot = sum(r.get("summary_chars", 0) for r in d.get("reports") or [])
    nst = sum(len(r.get("stances") or []) for r in d.get("reports") or [])
    nch = sum(len(r.get("charts") or []) for r in d.get("reports") or [])
    brk = "、".join(f"{k} {v}" for k, v in (d.get("brokers") or {}).items())

    L += [f"# 外資報告週摘　{w}", "",
          f"{rng[0]} ～ {rng[1]}　·　{d.get('reports_count', 0)} 份　·　{brk}", "",
          f"精華 {tot:,} 字　·　分析師原句 {nst} 筆　·　重製圖 {nch} 張", ""]

    L += ["## 本期報告", ""]
    for r in d.get("reports") or []:
        L.append(f"- [{r.get('broker','?')}｜{title_of(r)}](#{anchor(r['slug'])})"
                 f"　<sub>{r.get('date','')}　{r.get('pages','?')} 頁　"
                 f"{r.get('summary_chars',0):,} 字</sub>")
    L.append("")

    tg = d.get("tags") or {}
    if tg:
        L += ["## 本期標籤", "",
              "　".join(f"`{t}`（{len(sl)}）" if len(sl) > 1 else f"`{t}`"
                       for t, sl in tg.items()), ""]

    if d.get("crosscut"):
        L += ["## 交叉觀察", "", d["crosscut"].strip(), ""]

    if d.get("watch"):
        L += ["## 接下來看什麼", ""]
        L += [f"{i}. {x}" for i, x in enumerate(d["watch"], 1)]
        L.append("")

    L += ["---", ""]

    for r in d.get("reports") or []:
        L += [f'<a id="{anchor(r["slug"])}"></a>', "",
              f"## {r.get('broker','?')}｜{title_of(r)}", ""]
        meta = [r.get("date", ""), f"{r.get('pages','?')} 頁"]
        pr = r.get("product") or ""
        if pr and not title_of(r).startswith(pr):
            meta.insert(0, pr)
        if r.get("issue"):
            meta.append(str(r["issue"]))
        L.append("　·　".join(meta))
        L.append("")
        if r.get("tags"):
            L += ["　".join(f"`{t}`" for t in r["tags"]), ""]
        if r.get("file_url"):
            L += [f"📄 [開啟原始報告]({r['file_url']})　"
                  f"<sub>`{r.get('file','')}`</sub>", ""]

        L += [demote(r.get("summary", "").strip()), ""]

        cs = r.get("charts") or []
        if cs:
            L += ["### 重製圖表", ""]
            for c in cs:
                png = c.get("png")
                if png:
                    # 標題與副標已經畫在圖上了，這裡不再重複 —— 同一句話在三公分內
                    # 出現三次，讀的人會開始跳過那一區。渲染失敗時才需要文字補位。
                    L += [f"![{c.get('title','')}]({charts_dir}/{png})", ""]
                else:
                    L += [f"**{c.get('title','')}**", ""]
                    if c.get("subtitle"):
                        L += [c["subtitle"], ""]
                    L += [f"> 這張圖沒有渲染出來："
                          f"{c.get('render_error','原因未記錄')}", ""]
                L += [f"<sub>來源：{c.get('source','')}　·　"
                      f"依報告內文數字重製，非原圖翻拍</sub>", ""]

        ss = r.get("stances") or []
        if ss:
            L += ["### 分析師原句", "",
                  "| 主題 | 原句 | 中譯 | 頁 |", "| --- | --- | --- | --- |"]
            for s in ss:
                q = (s.get("quote") or "").replace("|", "\\|").replace("\n", " ")
                z = (s.get("quote_zh") or "").replace("|", "\\|").replace("\n", " ")
                L.append(f"| {s.get('theme','')} | {q} | {z} | "
                         f"{s.get('page','') if s.get('page') is not None else ''} |")
            L.append("")

        L += ["---", ""]

    if d.get("notes"):
        L += ["## 本期附註", ""]
        L += [f"- {x}" for x in d["notes"]]
        L.append("")

    L += ["<sub>精華與交叉觀察由 Claude 依報告內文整理，原句逐字引用並經機械比對；",
          "圖表依內文數字重製。原始報告不進版控，連結指向本機檔案。",
          f"組檔時間 {d.get('assembled_at','')}。</sub>", ""]
    return "\n".join(L)

CSS = """
:root{--bg:#fbfaf8;--fg:#1c1b19;--dim:#6b6862;--rule:#e2ddd5;--accent:#8c2f24}
@media (prefers-color-scheme:dark){
 :root{--bg:#16151a;--fg:#e9e6e1;--dim:#9b968e;--rule:#33313a;--accent:#e2695c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:17px/1.85 "Iowan Old Style","Songti TC","Noto Serif CJK TC",Georgia,serif;
 -webkit-font-smoothing:antialiased}
main{max-width:50rem;margin:0 auto;padding:3rem 1.5rem 6rem}
h1{font-size:2rem;line-height:1.3;margin:0 0 .3rem;letter-spacing:-.01em}
h2{font-size:1.5rem;line-height:1.35;margin:3.5rem 0 .8rem;
 padding-top:1.6rem;border-top:1px solid var(--rule)}
h3{font-size:1.15rem;margin:2.2rem 0 .5rem;color:var(--accent)}
h4{font-size:1rem;margin:1.6rem 0 .4rem}
p{margin:0 0 1.1rem}
a{color:inherit;text-decoration-color:var(--rule);text-underline-offset:3px}
a:hover{text-decoration-color:var(--accent)}
sub{font-size:.78em;color:var(--dim);vertical-align:baseline}
hr{display:none}
img{max-width:100%;height:auto;display:block;margin:1.2rem 0;border-radius:3px}
ul,ol{padding-left:1.4rem;margin:0 0 1.1rem}
li{margin:.3rem 0}
strong{font-weight:650}
table{border-collapse:collapse;width:100%;font-size:.86rem;line-height:1.6;
 font-family:-apple-system,"PingFang TC",system-ui,sans-serif;margin:0 0 1.4rem}
th,td{border-bottom:1px solid var(--rule);padding:.55rem .6rem;
 text-align:left;vertical-align:top}
th{font-weight:600;color:var(--dim);font-size:.78rem;letter-spacing:.03em;
 text-transform:uppercase;border-bottom-width:2px}
td:first-child{white-space:nowrap;color:var(--dim)}
td:last-child{text-align:right;color:var(--dim)}
.wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
code{font-size:.85em;background:var(--rule);padding:.1em .35em;border-radius:3px}
sub code{background:none;padding:0;font-size:.92em;color:var(--dim);word-break:break-all}
"""


def to_html(md, digest, charts_root):
    """把同一份 Markdown 轉成單一檔、可直接雙擊打開的 HTML。

    **圖用 base64 內嵌。** 相對路徑的圖在檔案被搬走、寄出、或用別的程式打開時
    會靜默變成破圖 —— 而一份少了圖的週摘，看起來跟本來就沒有圖的一模一樣。
    """
    try:
        import markdown as MD
    except ImportError:
        return None
    body = MD.markdown(md, extensions=["tables", "sane_lists"])

    def embed(m):
        f = os.path.join(charts_root, m.group(1))
        if not os.path.exists(f):
            return m.group(0)
        b64 = base64.b64encode(open(f, "rb").read()).decode()
        return f'src="data:image/png;base64,{b64}"'

    body = re.sub(r'src="charts/([^"]+)"', embed, body)
    body = re.sub(r"<table>", '<div class="wrap"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    title = f"外資報告週摘 {digest.get('week','')}"
    return ("<!doctype html>\n<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>{CSS}</style></head>"
            f"<body><main>\n{body}\n</main></body></html>\n")


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("digest")
    ap.add_argument("-o", "--out")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12
    d = json.load(open(a.digest, encoding="utf-8"))
    out = a.out or os.path.splitext(a.digest)[0] + ".md"
    print("\n".join(write_all(d, out)))
    return 0


def write_all(d, md_path):
    """寫 .md 與 .html。**兩份一起寫**，分開跑就會出現改了一份、另一份沒改。"""
    lines = []
    md = render(d)
    tmp = md_path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(md)
    os.replace(tmp, md_path)
    lines.append(f"→ {md_path}（{len(md):,} 字元）")

    h = to_html(md, d, os.path.join(os.path.dirname(md_path), "charts"))
    if h is None:
        lines.append("  （沒有 markdown 套件，這一輪不出 HTML —— "
                     "**這不是「不需要」，是缺件**：pip install markdown）")
        return lines
    hp = os.path.splitext(md_path)[0] + ".html"
    tmp = hp + ".tmp"
    open(tmp, "w", encoding="utf-8").write(h)
    os.replace(tmp, hp)
    lines.append(f"→ {hp}（{len(h) // 1024:,} KB，圖已內嵌）")
    return lines


if __name__ == "__main__":
    sys.exit(main())
