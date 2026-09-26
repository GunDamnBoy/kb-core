#!/usr/bin/env python3
"""notion-sync: copy every published issue of the five kb systems into Notion.

No model is involved: this reads the public data repos on GitHub and writes
through the official Notion API. Standard library only.

Usage
  python sync.py                    # sync everything that is new or changed
  python sync.py --dry-run --out DIR  # render only, write block JSON, no Notion calls
  python sync.py --systems podcast,broker --limit 3

Env
  NOTION_TOKEN   internal integration secret (required unless --dry-run)
  NOTION_DB_ID   產出庫 database id (default below)

Idempotency
  Each page carries 同步鍵 = "<repo>/<file>@<sha1-8>". A page is written as
  "PENDING:<key>" first and only renamed to "<key>" after every block landed,
  The key also records which layout wrote the page ("…@<hash>|v<RENDER_VERSION>");
  a page written by any other layout version is re-rendered on the next run,
  whatever its age, so a layout fix reaches the whole history exactly once.
  so an interrupted run leaves a PENDING page that the next run trashes and
  redoes. Issues whose content hash changed inside the recheck window
  (default 10 newest per system) are replaced.

Exit codes
  0  everything in scope is in Notion
  1  at least one issue failed (the rest were still synced)
  2  configuration / access problem (no token, database not shared, etc.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blocks import validate  # noqa: E402
from render import RENDER_VERSION, RENDERERS  # noqa: E402

DEFAULT_DB = "e60b58131b614d449a5fec9599646009"
NOTION = os.environ.get("NOTION_API_BASE", "https://api.notion.com/v1")  # override only for tests
NOTION_VERSION = "2022-06-28"
RAW = "https://raw.githubusercontent.com/GunDamnBoy/{repo}/main/{path}"

SYSTEMS = [
    # id,           repo,                        renderer,      site
    ("advisory", "advisory-rewrite", "advisory", "https://gundamnboy.github.io/advisory-rewrite/"),
    ("chart", "chart-of-the-day", "chart", "https://gundamnboy.github.io/chart-of-the-day/"),
    ("podcast", "podcast-knowledge-digest", "podcast",
     "https://gundamnboy.github.io/podcast-knowledge-digest/"),
    ("convergence", "convergence-weekly", "convergence",
     "https://gundamnboy.github.io/convergence-weekly/"),
    ("broker", "broker-research-digest", "broker",
     "https://gundamnboy.github.io/broker-research-digest/"),
]

P_TITLE, P_SYS, P_DATE, P_ISSUE = "標題", "系統", "日期", "期別"
P_REG, P_THEME, P_URL, P_KEY = "區域", "主題", "原站連結", "同步鍵"


class ConfigError(Exception):
    pass


# ------------------------------------------------------------------ http ----

def _get(url: str, cache_dir: str | None = None) -> bytes:
    if cache_dir:
        p = os.path.join(cache_dir, url.split("GunDamnBoy/")[1].replace("/main/", "/").replace("/", "__"))
        if os.path.exists(p):
            return open(p, "rb").read()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "kb-notion-sync"}),
                                        timeout=60) as r:
                data = r.read()
            if cache_dir:
                open(p, "wb").write(data)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed: {url}")


class Notion:
    def __init__(self, token: str):
        self.token = token
        self.calls = 0
        self._last = 0.0

    def req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(6):
            wait = 0.34 - (time.time() - self._last)          # ~3 req/s
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            rq = urllib.request.Request(NOTION + path, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(rq, timeout=90) as r:
                    self.calls += 1
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                txt = e.read().decode("utf-8", "replace")
                if e.code == 429 or e.code >= 500:
                    time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                    continue
                if e.code in (401, 403) or (e.code == 404 and "object_not_found" in txt):
                    raise ConfigError(f"{e.code} {txt[:300]}")
                raise RuntimeError(f"{method} {path} -> {e.code} {txt[:500]}")
            except urllib.error.URLError as e:
                time.sleep(2 ** attempt)
                last = e
        raise RuntimeError(f"{method} {path} failed after retries")


# ----------------------------------------------------------------- notion ---

def existing_pages(nt: Notion, db: str) -> tuple[dict[str, dict], list[str]]:
    """Return (sync-key-without-hash -> {id, hash}, page ids to trash).

    Pages still marked PENDING (an interrupted write) and duplicate complete
    pages for the same key are returned for trashing; one complete page per
    key is kept.
    """
    by_key: dict[str, list[dict]] = {}
    body: dict = {"page_size": 100}
    while True:
        r = nt.req("POST", f"/databases/{db}/query", body)
        for pg in r.get("results", []):
            rt = pg["properties"].get(P_KEY, {}).get("rich_text", [])
            raw = "".join(x.get("plain_text", "") for x in rt)
            if not raw:
                continue  # a page Kenny made by hand: never touch it
            pending = raw.startswith("PENDING:")
            key, _, rest = raw.removeprefix("PENDING:").partition("@")
            h, _, ver = rest.partition("|v")
            by_key.setdefault(key, []).append({"id": pg["id"], "hash": h, "ver": ver,
                                               "pending": pending})
        if not r.get("has_more"):
            break
        body["start_cursor"] = r["next_cursor"]
    keep: dict[str, dict] = {}
    drop: list[str] = []
    for key, pages in by_key.items():
        done = [p for p in pages if not p["pending"]]
        if done:
            keep[key] = done[0]
        drop += [p["id"] for p in pages if p is not keep.get(key)]
    return keep, drop


def _props(p: dict, key: str) -> dict:
    return {
        P_TITLE: {"title": [{"type": "text", "text": {"content": (p["title"] or "（無標題）")[:1900]}}]},
        P_SYS: {"select": {"name": p["system"]}},
        P_DATE: {"date": {"start": p["date"]}},
        P_ISSUE: {"rich_text": [{"type": "text", "text": {"content": str(p["issue"])[:1900]}}]},
        P_REG: {"multi_select": [{"name": x} for x in p["regions"]]},
        P_THEME: {"multi_select": [{"name": x} for x in p["themes"]]},
        P_URL: {"url": p["url"]},
        P_KEY: {"rich_text": [{"type": "text", "text": {"content": key}}]},
    }


def write_page(nt: Notion, db: str, props: dict, blocks: list[dict], key: str) -> str:
    pg = nt.req("POST", "/pages", {"parent": {"database_id": db},
                                   "properties": _props(props, "PENDING:" + key),
                                   "children": blocks[:100]})
    pid = pg["id"]
    for i in range(100, len(blocks), 100):
        nt.req("PATCH", f"/blocks/{pid}/children", {"children": blocks[i:i + 100]})
    nt.req("PATCH", f"/pages/{pid}", {"properties": {
        P_KEY: {"rich_text": [{"type": "text", "text": {"content": key}}]}}})
    return pid


def trash(nt: Notion, pid: str):
    nt.req("PATCH", f"/pages/{pid}", {"archived": True})


# ------------------------------------------------------------------- main ---

def issues_of(repo: str, cache: str | None):
    idx = json.loads(_get(RAW.format(repo=repo, path="data/index.json"), cache))
    days = idx.get("days", [])
    return [x.get("file") or f"data/{x['date']}.json" for x in days]  # newest first


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default=",".join(s[0] for s in SYSTEMS))
    ap.add_argument("--limit", type=int, default=0, help="max issues per system (newest first)")
    ap.add_argument("--recheck", type=int, default=10,
                    help="newest N issues per system are re-hashed and replaced if changed")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", help="dry-run: write rendered pages here")
    ap.add_argument("--cache", help="read/write fetched JSON here (testing)")
    a = ap.parse_args(argv)

    want = set(a.systems.split(","))
    db = os.environ.get("NOTION_DB_ID", DEFAULT_DB).replace("-", "")
    nt = None
    have: dict = {}
    if not a.dry_run:
        tok = os.environ.get("NOTION_TOKEN", "").strip()
        if not tok:
            print("::error::NOTION_TOKEN is not set", flush=True)
            return 2
        nt = Notion(tok)
        try:
            have, drop = existing_pages(nt, db)
            for pid in drop:  # interrupted writes and duplicates from earlier runs
                trash(nt, pid)
        except ConfigError as e:
            print(f"::error::Cannot read the 產出庫 database ({e}). "
                  "Is the page shared with the integration (… → 連結 → 新增連結)?", flush=True)
            return 2
        if drop:
            print(f"cleaned up {len(drop)} interrupted/duplicate page(s)", flush=True)

    if a.out:
        os.makedirs(a.out, exist_ok=True)
    stats = {"new": 0, "replaced": 0, "same": 0, "failed": 0, "blocks": 0}
    failures = []
    for sid, repo, rname, site in SYSTEMS:
        if sid not in want:
            continue
        try:
            files = issues_of(repo, a.cache)
        except Exception as e:
            failures.append(f"{sid}: index.json unreadable: {e}")
            stats["failed"] += 1
            continue
        if a.limit:
            files = files[:a.limit]
        for n, f in enumerate(files):
            key = f"{repo}/{f.split('/')[-1]}"
            known = have.get(key)
            current = bool(known) and known.get("ver") == RENDER_VERSION
            if current and n >= a.recheck:
                stats["same"] += 1
                continue
            try:
                raw = _get(RAW.format(repo=repo, path=f), a.cache)
                h = hashlib.sha1(raw).hexdigest()[:8]
                if current and known["hash"] == h:
                    stats["same"] += 1
                    continue
                props, blocks = RENDERERS[rname](json.loads(raw), repo, site)
                probs = validate(blocks)
                if probs:
                    raise RuntimeError("; ".join(probs[:5]))
                stats["blocks"] += len(blocks)
                if a.dry_run:
                    if a.out:
                        with open(os.path.join(a.out, key.replace("/", "__")), "w") as fh:
                            json.dump({"props": props, "blocks": blocks}, fh, ensure_ascii=False)
                    stats["new"] += 1
                    continue
                write_page(nt, db, props, blocks, f"{key}@{h}|v{RENDER_VERSION}")
                if known:
                    trash(nt, known["id"])
                    stats["replaced"] += 1
                else:
                    stats["new"] += 1
                print(f"  ✓ {key}  {len(blocks)} blocks  {props['regions']} {props['themes']}", flush=True)
            except ConfigError as e:
                print(f"::error::Notion refused access: {e}", flush=True)
                return 2
            except Exception as e:
                stats["failed"] += 1
                failures.append(f"{key}: {e}")
                print(f"::warning::{key}: {e}", flush=True)
    print(json.dumps({**stats, "notion_calls": nt.calls if nt else 0}, ensure_ascii=False), flush=True)
    for f in failures:
        print(f"::error::{f}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
