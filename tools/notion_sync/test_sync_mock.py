#!/usr/bin/env python3
"""End-to-end test of sync.py against a fake Notion API (no network, no token).

The fake enforces the real API's limits (≤100 children per call, ≤2000 chars
per text item, ≤100 rich_text items) and can inject failures. Scenarios:
  A  first run on an empty database writes every issue once
  B  second run is a no-op (idempotent)
  C  a write that dies half way leaves a PENDING page; next run trashes and redoes it
  D  an issue whose content changed (inside the recheck window) is replaced
  E  429 responses are retried
  F  a page Kenny created by hand (no 同步鍵) is never touched
  G  a layout-version bump re-renders the whole history once, then settles
"""
import json
import os
import shutil
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class Fake:
    def __init__(self):
        self.pages = {}          # id -> {props, blocks, archived}
        self.fail_append_after = None
        self.rate_limit_next = 0
        self.errors = []


FAKE = Fake()


def _check_blocks(children):
    if len(children) > 100:
        FAKE.errors.append(f"{len(children)} children in one call")
    for b in children:
        body = b[b["type"]]
        rt = body.get("rich_text", []) + body.get("caption", [])
        if len(rt) > 100:
            FAKE.errors.append("rich_text > 100")
        for r in rt:
            if len(r["text"]["content"]) > 2000:
                FAKE.errors.append("text > 2000")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _gate(self):
        if self.headers.get("Authorization") != "Bearer test-token":
            self._send(401, {"code": "unauthorized"})
            return False
        if FAKE.rate_limit_next:
            FAKE.rate_limit_next -= 1
            self._send(429, {"code": "rate_limited"}, {"Retry-After": "0"})
            return False
        return True

    def do_POST(self):
        if not self._gate():
            return
        b = self._body()
        if self.path.endswith("/query"):
            live = [(i, p) for i, p in FAKE.pages.items() if not p["archived"]]
            start = int(b.get("start_cursor") or 0)
            chunk = live[start:start + 100]
            res = [{"id": i, "properties": {k: _as_read(v) for k, v in p["props"].items()}}
                   for i, p in chunk]
            more = start + 100 < len(live)
            return self._send(200, {"results": res, "has_more": more,
                                    "next_cursor": str(start + 100) if more else None})
        if self.path == "/v1/pages":
            _check_blocks(b.get("children", []))
            pid = str(uuid.uuid4())
            FAKE.pages[pid] = {"props": b["properties"], "blocks": list(b.get("children", [])),
                               "archived": False}
            return self._send(200, {"id": pid})
        self._send(404, {"code": "object_not_found"})

    def do_PATCH(self):
        if not self._gate():
            return
        b = self._body()
        parts = self.path.strip("/").split("/")
        if parts[1] == "blocks":
            pid = parts[2]
            if FAKE.fail_append_after is not None:
                if FAKE.fail_append_after == 0:
                    FAKE.fail_append_after = None
                    return self._send(400, {"code": "validation_error", "message": "injected"})
                FAKE.fail_append_after -= 1
            _check_blocks(b["children"])
            FAKE.pages[pid]["blocks"] += b["children"]
            return self._send(200, {})
        if parts[1] == "pages":
            pid = parts[2]
            if b.get("archived"):
                FAKE.pages[pid]["archived"] = True
            for k, v in b.get("properties", {}).items():
                FAKE.pages[pid]["props"][k] = v
            return self._send(200, {"id": pid})
        self._send(404, {"code": "object_not_found"})


def _as_read(v):
    if "rich_text" in v:
        return {"rich_text": [{"plain_text": r["text"]["content"]} for r in v["rich_text"]]}
    return v


def live_keys():
    out = []
    for p in FAKE.pages.values():
        if p["archived"]:
            continue
        rt = p["props"].get("同步鍵", {}).get("rich_text", [])
        out.append("".join(r["text"]["content"] for r in rt))
    return out


def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["NOTION_API_BASE"] = f"http://127.0.0.1:{srv.server_port}/v1"
    os.environ["NOTION_TOKEN"] = "test-token"
    import sync  # noqa: E402  (reads NOTION_API_BASE at import)

    cache_src = sys.argv[1]
    cache = "/tmp/notion-sync-mock-cache"
    shutil.rmtree(cache, ignore_errors=True)
    shutil.copytree(cache_src, cache)
    args = ["--cache", cache, "--limit", "3"]
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name, detail)
        ok &= bool(cond)

    # F: a hand-made page
    FAKE.pages["manual"] = {"props": {"標題": {"title": []}}, "blocks": [], "archived": False}

    # A + E
    FAKE.rate_limit_next = 2
    rc = sync.main(args)
    keys = live_keys()
    check("A first run exit 0", rc == 0, f"rc={rc}")
    check("A 15 issues written (3 x 5 systems)", len([k for k in keys if k]) == 15, len(keys))
    check("A no PENDING left", not any(k.startswith("PENDING:") for k in keys))
    check("A API limits respected", not FAKE.errors, FAKE.errors[:3])
    big = max(FAKE.pages.values(), key=lambda p: len(p["blocks"]))
    check("A long pages fully appended", len(big["blocks"]) > 100, len(big["blocks"]))
    check("E 429 retried", FAKE.rate_limit_next == 0)

    # B
    n_before = len(FAKE.pages)
    rc = sync.main(args)
    check("B second run is a no-op", rc == 0 and len(FAKE.pages) == n_before, f"rc={rc}")

    # G: pages written by an older layout (no |v in the key) are all re-rendered,
    #    even outside the recheck window; the run after that is a no-op again
    for p in FAKE.pages.values():
        rt = p["props"].get("同步鍵", {}).get("rich_text", [])
        if rt and not p["archived"]:
            rt[0]["text"]["content"] = rt[0]["text"]["content"].split("|v")[0]
    live_before = len([k for k in live_keys() if k])
    rc = sync.main(args + ["--recheck", "1"])
    keys = [k for k in live_keys() if k]
    check("G old-layout pages all re-rendered", rc == 0 and len(keys) == live_before
          and all("|v" in k for k in keys), f"rc={rc} {len(keys)}/{live_before}")
    n_before = len(FAKE.pages)
    rc = sync.main(args + ["--recheck", "1"])
    check("G next run is a no-op", rc == 0 and len(FAKE.pages) == n_before, f"rc={rc}")

    # C: interrupted write
    victim_key = next(k for k in live_keys() if k.startswith("advisory-rewrite/"))
    vid = next(i for i, p in FAKE.pages.items() if not p["archived"] and
               "".join(r["text"]["content"] for r in p["props"].get("同步鍵", {}).get("rich_text", []))
               == victim_key)
    FAKE.pages[vid]["archived"] = True            # pretend it was never written...
    FAKE.fail_append_after = 1                    # ...and the rewrite dies after one append
    rc = sync.main(args)
    check("C interrupted run reports failure", rc == 1, f"rc={rc}")
    check("C leaves a PENDING page", any(k.startswith("PENDING:") for k in live_keys()))
    rc = sync.main(args)
    keys = live_keys()
    check("C next run heals", rc == 0 and not any(k.startswith("PENDING:") for k in keys)
          and keys.count(victim_key) == 1, f"rc={rc}")

    # D: changed content
    fn = os.path.join(cache, "chart-of-the-day__data__" + victim_key.split("/")[-1].split("@")[0]) \
        if False else None
    idx = json.load(open(os.path.join(cache, "chart-of-the-day__data__index.json")))
    newest = (idx["days"][0].get("file") or f"data/{idx['days'][0]['date']}.json").split("/")[-1]
    p = os.path.join(cache, f"chart-of-the-day__data__{newest}")
    d = json.load(open(p))
    d["headline"] = d["headline"] + "（更正版）"
    json.dump(d, open(p, "w"), ensure_ascii=False)
    rc = sync.main(args)
    chart_live = [k for k in live_keys() if k.startswith(f"chart-of-the-day/{newest}@")]
    titles = [pp["props"]["標題"]["title"][0]["text"]["content"] for pp in FAKE.pages.values()
              if not pp["archived"] and pp["props"].get("系統", {}).get("select", {}).get("name") == "每日五圖"]
    check("D changed issue replaced once", rc == 0 and len(chart_live) == 1
          and any("更正版" in t for t in titles), chart_live)

    check("F manual page untouched", not FAKE.pages["manual"]["archived"])
    check("limits held across all runs", not FAKE.errors, FAKE.errors[:3])
    srv.shutdown()
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
