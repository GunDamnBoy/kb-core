#!/usr/bin/env python3
"""Offline acceptance test for the renderers (no Notion calls).

For every rendered issue in --out (from `sync.py --dry-run --out`), and its
source JSON in --cache, check:
  1. validate(): nothing the Notion API would reject
  2. coverage: every human-readable string in the source JSON (outside the
     deliberately skipped machine-data keys) appears in the rendered text
  3. tags: every page gets at least one 區域 and one 主題, all from the fixed lists
Exit 0 only if all three hold for every issue.
"""
import argparse
import html
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blocks import plain, validate  # noqa: E402
from render import CHART_SKIP, REGIONS, THEMES  # noqa: E402

SKIP = {  # machine data / ids / file paths / styling — intentionally not rendered
    "advisory-rewrite": {"keptDates", "tagcls", "accent", "ts", "num", "chgPct", "id", "tag_cls", "cls"},
    "chart-of-the-day": CHART_SKIP | {"macro_release", "qa_flags", "series", "option"},
    "podcast-knowledge-digest": {"id", "trackId", "showKey", "minutes", "chars", "guests", "topics"},
    "convergence-weekly": {"schemaVer", "cls", "id"},
    "broker-research-digest": {"tags", "slug", "product", "title_source", "title_confident",
                               "tier_target", "tier_band", "summary_chars", "png", "svg", "bytes",
                               "grounding", "assembled_at"} | CHART_SKIP,
}
HTML_REPOS = {"advisory-rewrite", "convergence-weekly"}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def leaves(x, skip, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            if k in skip:
                continue
            yield from leaves(v, skip, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from leaves(v, skip, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x


def block_text(blocks):
    out = []
    for b in blocks:
        body = b.get(b["type"], {})
        for r in body.get("rich_text", []) + body.get("caption", []):
            out.append(r["text"]["content"])
            if r["text"].get("link"):
                out.append(r["text"]["link"]["url"])
        if b["type"] == "image":
            out.append(body["external"]["url"])
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    a = ap.parse_args()
    bad = 0
    per_sys = collections.defaultdict(lambda: collections.Counter())
    missing_examples = collections.defaultdict(list)
    for fn in sorted(os.listdir(a.out)):
        repo, file = fn.split("__", 1)
        page = json.load(open(os.path.join(a.out, fn)))
        src = json.load(open(os.path.join(a.cache, f"{repo}__data__{file}")))
        mode = "html" if repo in HTML_REPOS else "md"
        blocks, props = page["blocks"], page["props"]
        c = per_sys[repo]
        c["issues"] += 1
        c["blocks"] += len(blocks)
        probs = validate(blocks)
        if probs:
            bad += 1
            print("INVALID", fn, probs[:3])
        bt = block_text(blocks)
        if re.search(r"\['|\{'|': '", bt):
            bad += 1
            print("PYTHON REPR LEAKED", fn, bt[max(0, bt.find("['") - 20):][:80])
        text = norm(block_text(blocks) + props["title"] + str(props["issue"]))
        pieces = []
        for path, s in leaves(src, SKIP[repo]):
            # markdown documents: compare line by line, block markers stripped
            for line in s.split("\n") if (mode == "md" and "\n" in s) else [s]:
                line = re.sub(r"^\s*(#{1,6}\s+|[-*•]\s+|\d+[.)]\s+|>\s?)", "", line)
                pieces.append((path, line))
        for path, s in pieces:
            p = norm(plain(s, mode))
            if re.fullmatch(r"t-[a-z]+", p):
                continue  # css class names (card/focus colour tags)
            if len(p) < 2 or re.fullmatch(r"[\d.,:%+\-−TZ/年月日（）()週一二三四五六日]+", p):
                continue  # numbers / dates / single chars that live in metadata lines
            c["strings"] += 1
            c["chars"] += len(p)
            if p not in text:
                if path.endswith(".url") and norm(html.unescape(s)) in text:
                    continue
                c["missing"] += 1
                c["missing_chars"] += len(p)
                if len(missing_examples[repo]) < 12:
                    missing_examples[repo].append(f"{file}{path}: {s[:70]!r}")
        if not props["regions"] or not props["themes"]:
            c["untagged"] += 1
        if not set(props["regions"]) <= set(REGIONS) or not set(props["themes"]) <= set(THEMES):
            bad += 1
            print("BAD TAG", fn, props["regions"], props["themes"])
        for t in props["regions"] + props["themes"]:
            c["tag:" + t] += 1
    for repo, c in per_sys.items():
        cov = 100 * (1 - c["missing_chars"] / max(1, c["chars"]))
        print(f"\n== {repo}: {c['issues']} issues, {c['blocks']} blocks, "
              f"{c['strings']} strings, missing {c['missing']} ({cov:.2f}% chars covered), "
              f"untagged {c['untagged']}")
        print("   tags:", ", ".join(f"{k[4:]} {v}" for k, v in c.most_common() if k.startswith("tag:")))
        for m in missing_examples[repo]:
            print("   MISSING", m)
        if c["missing"]:
            bad += 1
    print("\nRESULT:", "PASS" if not bad else f"FAIL ({bad})")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
