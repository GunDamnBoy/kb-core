"""Text -> Notion block helpers (stdlib only).

Inline markup handled:
  html mode      <b>/<strong> bold, <i>/<em> italic, <code>, <a href>, <br>, entities;
                 any other tag is dropped but its inner text is kept.
  markdown mode  **bold**, *italic*, `code`, [text](url); '<' and '>' are literal text.
Block markdown (md_blocks): #/##/### headings, - / * bullets, 1. numbered, > quote,
blank-line separated paragraphs.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

MAX_TEXT = 2000        # Notion: chars per rich_text item
MAX_SEGMENTS = 100     # Notion: rich_text items per block
MAX_URL = 2000


# ---------------------------------------------------------------- inline ----

class _Inline(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.segs: list[tuple[str, dict, str | None]] = []
        self.bold = self.italic = self.code = 0
        self.link: list[str | None] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("b", "strong"):
            self.bold += 1
        elif tag in ("i", "em"):
            self.italic += 1
        elif tag == "code":
            self.code += 1
        elif tag == "a":
            self.link.append(dict(attrs).get("href"))
        elif tag == "br":
            self.handle_data("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.handle_data("\n")

    def handle_endtag(self, tag):
        if tag in ("b", "strong"):
            self.bold = max(0, self.bold - 1)
        elif tag in ("i", "em"):
            self.italic = max(0, self.italic - 1)
        elif tag == "code":
            self.code = max(0, self.code - 1)
        elif tag == "a" and self.link:
            self.link.pop()

    def handle_data(self, data):
        if not data:
            return
        ann = {"bold": self.bold > 0, "italic": self.italic > 0, "code": self.code > 0}
        link = next((l for l in reversed(self.link) if l), None)
        self.segs.append((data, ann, link))


_MD_CODE = re.compile(r"`([^`\n]+)`")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_MD_ITAL = re.compile(r"(?<![\*\w])\*(?![\s\*])([^*\n]+?)(?<!\s)\*(?![\*\w])")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def _md_to_html(s: str, escape: bool) -> str:
    if escape:
        s = html.escape(s, quote=False)
    codes: list[str] = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = _MD_CODE.sub(keep, s)
    s = _MD_LINK.sub(lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
    s = _MD_BOLD.sub(r"<b>\1</b>", s)
    s = _MD_ITAL.sub(r"<i>\1</i>", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s


def rich(text, mode: str = "md", bold: bool = False, italic: bool = False,
         color: str | None = None) -> list[dict]:
    """Return a list of Notion rich_text objects (may exceed 100; see para())."""
    if text is None:
        return []
    if isinstance(text, (list, tuple, dict)):  # never let a Python repr reach Notion
        vals = text.values() if isinstance(text, dict) else text
        text = "\n".join(plain(v, mode) if not isinstance(v, str) else v for v in vals if v not in (None, ""))
    text = str(text)
    if mode == "plain":
        segs = [(text, {"bold": False, "italic": False, "code": False}, None)]
    else:
        src = _md_to_html(text, escape=(mode == "md"))
        p = _Inline()
        p.feed(src)
        p.close()
        segs = p.segs
    # merge neighbours with identical style
    merged: list[list] = []
    for t, ann, link in segs:
        if merged and merged[-1][1] == ann and merged[-1][2] == link:
            merged[-1][0] += t
        else:
            merged.append([t, dict(ann), link])
    out = []
    for t, ann, link in merged:
        if bold:
            ann["bold"] = True
        if italic:
            ann["italic"] = True
        if link and (len(link) > MAX_URL or not link.startswith(("http://", "https://"))):
            link = None
        for i in range(0, len(t), MAX_TEXT):
            chunk = t[i:i + MAX_TEXT]
            obj = {"type": "text", "text": {"content": chunk}}
            if link:
                obj["text"]["link"] = {"url": link}
            a = {k: v for k, v in ann.items() if v}
            if color:
                a["color"] = color
            if a:
                obj["annotations"] = a
            out.append(obj)
    return out


def plain(text, mode: str = "md") -> str:
    return "".join(r["text"]["content"] for r in rich(text, mode))


# ----------------------------------------------------------------- blocks ---

def _text_blocks(btype: str, rt: list[dict], extra: dict | None = None) -> list[dict]:
    """One logical block; split into several if it has >100 rich_text items."""
    if not rt:
        return []
    out = []
    for i in range(0, len(rt), MAX_SEGMENTS):
        body = {"rich_text": rt[i:i + MAX_SEGMENTS]}
        if extra:
            body.update(extra)
        out.append({"object": "block", "type": btype, btype: body})
    return out


def para(text, mode="md", **kw):
    if isinstance(text, (list, tuple)):  # a list of paragraphs
        return [blk for t in text for blk in para(t, mode, **kw)]
    return _text_blocks("paragraph", rich(text, mode, **kw))


def para_rt(rt):
    return _text_blocks("paragraph", rt)


def heading(level: int, text, mode="md"):
    level = min(max(level, 1), 3)
    rt = rich(text, mode)
    for r in rt:  # headings are already bold; keep italics/code only
        r.get("annotations", {}).pop("bold", None)
    return _text_blocks(f"heading_{level}", rt)


def bullet(text, mode="md", **kw):
    return _text_blocks("bulleted_list_item", rich(text, mode, **kw))


def bullet_rt(rt):
    return _text_blocks("bulleted_list_item", rt)


def numbered(text, mode="md"):
    return _text_blocks("numbered_list_item", rich(text, mode))


def quote(text, mode="md"):
    return _text_blocks("quote", rich(text, mode))


def quote_rt(rt):
    return _text_blocks("quote", rt)


def callout(text, emoji="📌", mode="md", color="gray_background"):
    return _text_blocks("callout", rich(text, mode),
                        {"icon": {"type": "emoji", "emoji": emoji}, "color": color})


def divider():
    return [{"object": "block", "type": "divider", "divider": {}}]


def image(url: str, caption: str | None = None):
    if not url or not url.startswith("https://"):
        return []
    body = {"type": "external", "external": {"url": url}}
    if caption:
        body["caption"] = rich(caption, "plain")[:MAX_SEGMENTS]
    return [{"object": "block", "type": "image", "image": body}]


def link_para(label: str, url: str | None):
    if not url or not url.startswith(("http://", "https://")) or len(url) > MAX_URL:
        return []
    return para_rt([{"type": "text", "text": {"content": label, "link": {"url": url}}}])


def meta(text):
    """Small grey line for provenance / metadata."""
    return para(text, "md", color="gray")


_H = re.compile(r"^(#{1,6})\s+(.*)$")
_UL = re.compile(r"^\s*[-*•]\s+(.*)$")
_OL = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QT = re.compile(r"^\s*>\s?(.*)$")


def md_blocks(text, heading_base: int = 3, mode: str = "md") -> list[dict]:
    """Markdown document -> blocks. heading_base: level used for '#'."""
    if text is None:
        return []
    text = str(text).replace("\r\n", "\n")
    out: list[dict] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.extend(para("\n".join(buf), mode))
            buf.clear()

    for line in text.split("\n"):
        if not line.strip():
            flush()
            continue
        m = _H.match(line)
        if m:
            flush()
            out.extend(heading(min(3, heading_base + len(m.group(1)) - 1), m.group(2), mode))
            continue
        m = _UL.match(line)
        if m and not line.lstrip().startswith("**"):
            flush()
            out.extend(bullet(m.group(1), mode))
            continue
        m = _OL.match(line)
        if m:
            flush()
            out.extend(numbered(m.group(1), mode))
            continue
        m = _QT.match(line)
        if m:
            flush()
            out.extend(quote(m.group(1), mode))
            continue
        buf.append(line)
    flush()
    return out


def validate(blocks: list[dict]) -> list[str]:
    """Return problems that the Notion API would reject."""
    probs = []
    for i, b in enumerate(blocks):
        t = b.get("type")
        body = b.get(t, {})
        rt = body.get("rich_text") or body.get("caption") or []
        if len(rt) > MAX_SEGMENTS:
            probs.append(f"block {i} {t}: {len(rt)} rich_text items")
        for r in rt:
            c = r["text"]["content"]
            if len(c) > MAX_TEXT:
                probs.append(f"block {i} {t}: text {len(c)} chars")
            ln = r["text"].get("link")
            if ln and len(ln["url"]) > MAX_URL:
                probs.append(f"block {i} {t}: link too long")
        if t in ("paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
                 "numbered_list_item", "quote", "callout") and not body.get("rich_text"):
            probs.append(f"block {i} {t}: empty rich_text")
    return probs
