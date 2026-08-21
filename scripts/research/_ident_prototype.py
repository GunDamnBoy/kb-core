# 辨識層原型：**只讀不寫、只印結果。** 打得中七份才有資格變成 kb-core 裡的程式。
import glob, os, re, sys, json
import pdfplumber

# 浮水印有兩種形態，取決於抽取器怎麼處理旋轉文字：
#   pdftotext  → "For the exclusive use of xxx@yyy"、"Prepared for James Hua"（正著）
#   pdfplumber → "evisulcxe"、"semaJ"、"deraperP"（倒著，逐段反轉）
# **兩種都要剃**，因為兩條抽取路徑都可能被走到。
WM = [
    re.compile(r"For the exclusive use of\s+\S+", re.I),
    re.compile(r"Prepared for\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", re.I),
    re.compile(r"\b(?:evisulcxe|deraperP|semaJ)\b"),
    re.compile(r"\b[0-9a-f]{32}\b"),                       # 逐份追蹤雜湊（正反皆同形）
    re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"),              # 任何信箱，含反寫過的
    re.compile(r"\bWT\.MOC\.[A-Z]+@\d+\b"),                # 反寫的信箱
]

BROKERS = [                       # (顯示名, 頁首指紋)
    ("Nomura",        re.compile(r"\bNomura\s*\|", re.I)),
    ("Goldman Sachs", re.compile(r"\bGoldman\s+Sachs\b", re.I)),
    ("Citi",          re.compile(r"\bCiti\s*(?:Research|group)\b", re.I)),
]

DATES = [
    (re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2,8}\s+20\d\d)\b"), "%d %B %Y"),   # 20 August 2026
    (re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+20\d\d)\b"),   "%d %b %Y"),   # 20 Aug 2026
    (re.compile(r"\b([A-Z][a-z]{2,8}\s+\d{1,2},\s+20\d\d)\b"), "%B %d, %Y"), # August 19, 2026
]


def clean(t):
    for p in WM:
        t = p.sub(" ", t)
    return t


def ident(path):
    with pdfplumber.open(path) as pdf:
        npage = len(pdf.pages)
        p1 = clean(pdf.pages[0].extract_text(layout=True) or "")
        # 券商指紋要在**任一頁的頁首**找，不是只看第一頁——高盛第 1 頁沒有 "Goldman Sachs"
        head = clean("\n".join((pdf.pages[i].extract_text() or "")[:400]
                               for i in range(min(4, npage))))
    broker = next((n for n, p in BROKERS if p.search(head) or p.search(p1)), None)

    import datetime as dt
    date = None
    for rx, fmt in DATES:
        m = rx.search(p1)
        if m:
            try:
                date = dt.datetime.strptime(m.group(1), fmt).date().isoformat(); break
            except ValueError:
                pass

    base = os.path.basename(path).replace(".pdf", "").strip()
    product = base.split("_")[0].strip() if "_" in base else base
    issue = (re.search(r"ISSUE\s+(\d+)", p1) or [None, None])[1]
    claimed = (re.search(r"│?\s*(\d+)\s+pages", p1) or [None, None])[1]

    lines = [l.strip() for l in p1.splitlines() if l.strip()]
    return dict(file=base[:44], broker=broker, product=product, date=date,
                pages=npage, claimed_pages=claimed and int(claimed), issue=issue,
                p1_chars=len(p1), p1_lines=len(lines))


rows = [ident(p) for p in sorted(glob.glob(sys.argv[1] + "/*.pdf"))]
w = max(len(r["file"]) for r in rows)
print(f"{'檔':<{w}}  {'券商':<14} {'日期':<11} {'頁':>4} {'自報':>4} {'期號':>5} {'p1字元':>7}")
for r in rows:
    print(f"{r['file']:<{w}}  {str(r['broker'] or '**認不出**'):<14} "
          f"{str(r['date'] or '**認不出**'):<11} {r['pages']:>4} "
          f"{str(r['claimed_pages'] or '-'):>4} {str(r['issue'] or '-'):>5} {r['p1_chars']:>7}")
n = len(rows)
print(f"\n券商 {sum(1 for r in rows if r['broker'])}/{n}　"
      f"日期 {sum(1 for r in rows if r['date'])}/{n}　"
      f"自報頁數對得上 {sum(1 for r in rows if r['claimed_pages'] == r['pages'])}"
      f"/{sum(1 for r in rows if r['claimed_pages'])}")
