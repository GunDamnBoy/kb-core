#!/usr/bin/env python3
"""掃描式量測：**三個界線全部量到，不靠任何一輪自己宣告。**

## 為什麼不用 sidecar 就好

sidecar 那條路（`launchd/kbusage.sh`）本身沒有問題，**但它要求七套的執行指示
各自帶一步**，而 2026-08-24 查證的結果是：**每天真的在跑的那一份，沒有一份是
kb-core 裡的正本。** 帳號 skill `advisory-daily` 是 138 行、`updatedAt` 停在
08-19，而 `skills/advisory/SKILL.md` 是 389 行、當天才寫進用量那一節 ——
**整份 grep 不到「用量」兩個字。** 正本接上了，執行的那份副本沒跟上。

所以 sidecar 路線的真實成本不是「改六個檔」，是「改七個正本 ＋ 手動重新部署
七份副本」，而且**每一次改都會再漂一次**。這一支改成從外面量，
**不需要任何一份副本跟上**。

## 三個界線各自的出處

| | 出處 | 為什麼它是量到的 |
|---|---|---|
| 下界 | 逐字稿的第一筆 | **排程開的是全新對話、沒有任何記憶**（advisory 與 podcast 的正本都這樣寫），所以第一筆就是那一輪的開始 |
| 上界 | 日檔**第一次被 commit** 的時間 | 發布後不可改寫，**重發是新的 commit、第一次那顆不會動**。回執的 `at` 會被每一次 publish 覆寫 —— 2026-08-22 那期差 613 分鐘 |
| 是哪一套 | 逐字稿內容裡的 `<日期>.draft.json` 路徑 | 那是那一輪自己寫出去的檔，路徑帶著 outbox 子目錄。**命中不唯一就報缺口，不硬寫** |

上界的誤差是「草稿落地 → publish 撿到」那 1–3 分鐘（`kbpublish.*` 每 60 秒掃
一次、外加靜置），比 2026-08-24 修掉的那 23 分鐘小一個數量級。

## repo 路徑不另外登記，從 plist 讀

`launchd/com.kenny.kbpublish*.plist` 的 `ProgramArguments` 已經寫著
`publish.py <outbox> <資料 repo> <id>`，而 `OUTBOX_DIR` 已經把系統 id 對到
outbox 子目錄 —— 兩者用 outbox 路徑接得起來。**再開一張表就是第三個會過期的地方。**

沒有 kbpublish plist 的兩套（`bubble` 走自己的 `auto_publish.py`、
`houseview` 是手動啟動）沒有 `data/<日期>.json` 可查，退回用回執的 `at`
當上界，**並在報告裡講明那一列的上界是鬆的**。

## 它不覆蓋既有的列

CSV 上已經有那一天那一套，就跳過 —— sidecar 那條路量得更精準
（輪次自己知道它什麼時候交草稿），有就讓它贏。
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import plistlib
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from usage_report import SYSTEMS, OUTBOX_DIR                      # noqa: E402
from usage_gaps import TPE, receipt_path, has_row                 # noqa: E402

SESSIONS = ("~/Library/Application Support/Claude/local-agent-mode-sessions")


def repo_by_outbox(launchd_dir: str) -> dict:
    """從 kbpublish 的 plist 讀出 `{outbox 絕對路徑: 資料 repo 絕對路徑}`。

    **這裡不解析系統 id**，因為 publish 的 id（`advisory-knowledge-hub`）與
    用量的系統 id（`advisory`）不是同一組值域 —— 用 outbox 路徑接，
    那是兩邊都真的有的東西。
    """
    out = {}
    for f in sorted(glob.glob(os.path.join(launchd_dir, "com.kenny.kbpublish*.plist"))):
        try:
            args = plistlib.load(open(f, "rb"))["ProgramArguments"]
        except Exception:
            continue
        # python publish.py <outbox> <repo> <id>
        hit = [i for i, a in enumerate(args) if a.endswith("publish.py")]
        if not hit or len(args) < hit[0] + 3:
            continue
        i = hit[0]
        out[os.path.normpath(args[i + 1])] = os.path.normpath(args[i + 2])
    return out


def commit_on_date(repo: str, rel: str, date: str):
    """那個日檔在**那一天**最早的那一顆 commit，回 `(ISO8601, hash)`；沒有回 `(None, None)`。

    **不是「首次 commit」。** 2026-08-24 乾跑實測抓到這個差別：
    `broker-research-digest` 裡 `data/2026-08-23.json` 的首次 commit 是
    **08-22 06:47** —— 週摘依報告自己的日期分期，同一個日檔會在那一週裡被
    改寫好幾次（`republish_rule` 對週頻是允許的）。拿首次 commit 當上界，
    界線會落在那一輪開始之前，**整場被切光**。

    改成「那一天最早的那一顆」之後兩種都對：
    · 日頻：那一天只有一顆新增 commit，取到的就是它
    · 週頻：取到那一輪自己那一次改寫
    · 同一天重發：取**最早**那顆，所以 2026-08-22 那期 613 分鐘的偏移進不來
    """
    try:
        r = subprocess.run(["git", "-C", repo, "log", "--format=%aI %H", "--", rel],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None, None
    same = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            d = dt.datetime.fromisoformat(parts[0])
        except ValueError:
            continue
        h = parts[1]
        if d.astimezone(TPE).date().isoformat() == date:
            same.append((d, h))
    if not same:
        return None, None
    # **回字串不回 datetime** —— 它會被原樣交給 `usage_report.py --until`，
    # 而 `str(datetime)` 用空白分隔日期與時間，`_norm_iso()` 收不下。
    d, h = min(same)
    return d.isoformat(), h


def window_to(repo: str, rel: str, commit: str):
    """那一顆 commit 當下的日檔裡的 `window.to`。沒有就回 None。

    **這是輪次自己寫的、發布後不可改寫的那個值** —— 也就是 sidecar 會給的
    同一個字串。日檔已經在資料 repo 裡，所以掃描讀得到它，
    **不需要任何一份執行副本跟上**。

    為什麼用 `git show <commit>:<檔>` 而不是直接讀工作區：週頻的日檔會被改寫，
    工作區那份的 `window.to` 是**最後一次**改寫的，不是那一輪的。
    """
    try:
        r = subprocess.run(["git", "-C", repo, "show", f"{commit}:{rel}"],
                           capture_output=True, text=True, timeout=30)
        doc = json.loads(r.stdout)
    except Exception:
        return None

    def find(o):
        if isinstance(o, dict):
            w = o.get("window")
            if isinstance(w, dict) and w.get("to"):
                return w["to"]
            for v in o.values():
                got = find(v)
                if got:
                    return got
        elif isinstance(o, list):
            for v in o:
                got = find(v)
                if got:
                    return got
        return None
    return find(doc)


def index_transcripts(sessions: str, markers_by_date: dict) -> dict:
    """掃**一次**，回 `{(日期, marker): [路徑…]}`。

    **一次掃完所有日期的所有標記。** 逐字稿動輒數 MB，回填八天若每天各讀一遍，
    就是八倍的 I/O 讀同一批檔案 —— 而一份逐字稿只屬於一個日期，
    先算出它是哪一天，再只比對那一天的標記就好。

    只收**開在那一天**（台北）的那些：維護對話也可能提到同一個草稿路徑，
    但它通常開在別天。同一天而且也提到的話，由 `pick()` 的「不唯一就不寫」擋下來。
    """
    hits = {}
    for p in glob.glob(os.path.join(sessions, "*", "*", "local_*", ".claude",
                                    "projects", "*", "*.jsonl")):
        if os.sep + "subagents" + os.sep in p:
            continue
        # **先讀第一行、判日期，不在範圍內就不讀本文。**
        # 一份主逐字稿可以是好幾 MB，而一台機器上會累積幾百份 ——
        # 整份讀進來再判日期，等於把不相干的那幾百份也讀一遍。
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                head_line = f.readline()
                try:
                    first = json.loads(head_line).get("timestamp") or ""
                    d = dt.datetime.fromisoformat(first.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                day = d.astimezone(TPE).date().isoformat()
                wanted = markers_by_date.get(day)
                if not wanted:
                    continue
                text = head_line + f.read()
        except OSError:
            continue
        for m in wanted:
            if m in text:
                hits.setdefault((day, m), []).append(p)
    return hits


def pick(hits, date: str, marker: str):
    """`(路徑, 說明)`。**恰好一份才回路徑**，其餘一律回 None 與原因。"""
    c = hits.get((date, marker)) or []
    if len(c) == 1:
        return c[0], None
    if not c:
        return None, f"沒有逐字稿提到 `{marker}` 且開在 {date}"
    return None, ("**%d 份逐字稿都符合，不唯一就不寫**：%s"
                  % (len(c), "、".join(os.path.basename(x) for x in c)))


def scan_one(date, cfg, hits):
    """掃一天。回 `(量到, 乾跑, 失敗)`。"""
    csv, outbox, py, repos, dry = (cfg["csv"], cfg["outbox"], cfg["py"],
                                   cfg["repos"], cfg["dry"])
    done = skipped = failed = 0
    lines = []
    for s in SYSTEMS:
        rp = receipt_path(outbox, s, date)
        if rp is None or not os.path.exists(rp):
            continue                                   # 那天沒跑
        if has_row(csv, s, date):
            lines.append(f"  ⏭️  {s} 已經有列")
            continue
        try:
            code = json.load(open(rp, encoding="utf-8")).get("exit")
        except Exception:
            code = None
        if isinstance(code, int) and code != 0:
            lines.append(f"  ⏭️  {s} 那一輪 publish 失敗（exit={code}），沒有草稿可切界線")
            continue

        sub = OUTBOX_DIR.get(s) or ""
        repo = repos.get(os.path.normpath(os.path.join(outbox, sub)))
        if not repo:
            # **這一套不走 `tools/publish.py`**（bubble 有自己的 auto_publish.py、
            # houseview 是手動啟動的整合檢查），所以沒有 `data/<日期>.json` 可查。
            # 退回回執的 `at` 是可以的，但那正是 613 分鐘那個坑 ——
            # **與其寫一列上界是猜的，不如講清楚它要走 sidecar。**
            lines.append(f"  ⏭️  {s} 不走 tools/publish.py，沒有日檔可切上界"
                         f" —— 要量得靠 sidecar")
            continue
        rel = f"data/{date}.json"
        at, h = commit_on_date(repo, rel, date)
        if not at:
            lines.append(f"  ❌ {s} {os.path.basename(repo)} 裡 {rel} "
                         f"當天沒有任何 commit —— 沒有上界就不硬切")
            failed += 1
            continue

        # **上界的優先序：輪次自己寫的 > 發布管線給的。**
        # 2026-08-24 實測，這兩者在發布卡住的那天差 23 分鐘、多算 22% 的 token
        # （36,030k vs 29,431k）—— 而 commit 是「publish 成功的時刻」，
        # 那天它被一個沒提交的工作區擋到 10:04。**平常只差一兩分鐘，
        # 所以它壞掉的那天不會有人發現。**
        until = window_to(repo, rel, h)
        src = "window"
        if until:
            src_txt = "window.to"
        else:
            until, src = at, "commit"
            src_txt = "當天最早 commit（publish 成功的時刻，不是交草稿的時刻）"

        tp, why = pick(hits, date, cfg["marker"][(date, s)])
        if tp is None:
            lines.append(f"  ❌ {s} 找不到唯一的逐字稿 —— {why}")
            failed += 1
            continue

        lines.append(f"  ▶︎ {s}　{os.path.basename(tp)}")
        lines.append(f"      上界 {until}（{src_txt}）")
        if dry:
            skipped += 1
            continue
        r = subprocess.run([py, os.path.join(HERE, "usage_report.py"), s,
                            "--transcript", tp, "--until", until,
                            "--date", date, "--bound-src", src, "--append", csv],
                           capture_output=True, text=True)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        lines.append(f"      {'✅' if r.returncode == 0 else '❌'} {tail[0]}")
        done += r.returncode == 0
        failed += r.returncode != 0

    if lines:
        print(f"── {date}")
        print("\n".join(lines))
    return done, skipped, failed


def main():
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--date", default=None, help="要掃的那一天，預設是台北的昨天")
    ap.add_argument("--days", type=int, default=1, metavar="N",
                    help="從 --date 往前掃 N 天（含當天）。回填用。"
                         "**逐字稿與 git 歷史都還在，所以回填的列與新列出處相同、"
                         "可以直接比** —— 這是把逐套優化提前兩週開工的唯一動作。")
    ap.add_argument("--csv", default="~/kb-core/metrics/usage.csv")
    ap.add_argument("--outbox", default="~/outbox")
    ap.add_argument("--sessions", default=SESSIONS)
    ap.add_argument("--launchd", default=os.path.join(os.path.dirname(HERE), "launchd"))
    ap.add_argument("--python", default="~/.venvs/kb/bin/python")
    ap.add_argument("--dry-run", action="store_true",
                    help="只印要做什麼與界線的出處，**不寫 CSV**。第一次跑用它。")
    a, unknown = ap.parse_known_args()
    if unknown:
        print(f"不認得的旗標：{' '.join(unknown)}", file=sys.stderr)
        return 12
    if a.days < 1:
        print("--days 至少是 1", file=sys.stderr)
        return 12

    end = a.date or (dt.datetime.now(TPE).date() - dt.timedelta(days=1)).isoformat()
    try:
        end_d = dt.date.fromisoformat(end)
    except ValueError:
        print(f"--date 要 YYYY-MM-DD，收到 {end!r}", file=sys.stderr)
        return 12
    dates = [(end_d - dt.timedelta(days=i)).isoformat() for i in range(a.days)][::-1]

    cfg = {"csv": os.path.expanduser(a.csv), "outbox": os.path.expanduser(a.outbox),
           "py": os.path.expanduser(a.python), "repos": repo_by_outbox(a.launchd),
           "dry": a.dry_run, "marker": {}}
    if not os.path.exists(cfg["csv"]):
        print(f"讀不到 {cfg['csv']} —— 這是環境問題，不是「沒有要量的」", file=sys.stderr)
        return 14

    markers_by_date = {}
    for d in dates:
        for sysid in SYSTEMS:
            sub = OUTBOX_DIR.get(sysid) or ""
            m = os.path.join("outbox", sub, f"{d}.draft.json")
            cfg["marker"][(d, sysid)] = m
            markers_by_date.setdefault(d, set()).add(m)
    hits = index_transcripts(os.path.expanduser(a.sessions), markers_by_date)

    tot = [0, 0, 0]
    for d in dates:
        got = scan_one(d, cfg, hits)
        tot = [x + y for x, y in zip(tot, got)]

    span = dates[0] if len(dates) == 1 else f"{dates[0]} → {dates[-1]}"
    print(f"\n{span}：量到 {tot[0]}、乾跑 {tot[1]}、失敗 {tot[2]}")
    return 12 if tot[2] else 0


if __name__ == "__main__":
    sys.exit(main())
