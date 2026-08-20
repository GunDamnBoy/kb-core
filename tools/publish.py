#!/usr/bin/env python3
"""publish —— 唯一的發布路徑。跑在 Mac 上，由 launchd 觸發。

用法：publish.py <outbox> <資料 repo> <系統 id>

流程：目的地守門 → 掃 outbox → verify（閘門）→ 不可改寫守衛 → 原子寫入
      data/ → 更新 index → pull --rebase → commit → push → 寫回執

六條刻意的設計：

1. **verify 擋在寫入 data/ 之前。** 雲端那次 verify 是給 judge 段即時回饋，
   這一次才是閘門。同一份檢查程式跑兩次，不違反單錨。

2. **不可改寫守衛。** data/<date>.json 已存在且內容不同 → exit 11，不覆寫。
   「已發布的一期就是已發布的樣子」——要更正就掛 errata，不是改內文。

3. **push 前一定 pull --rebase，且絕不 force。** 兩個寫入者共用 main，
   遠端比我新是常態不是意外。force 會抹掉 Actions 剛寫進去的 raw。

4. **每一輪都寫回執。** 成功或失敗都寫，因為「沒有回執」與「回執說失敗」
   是兩件不同的事——前者代表 publish 根本沒跑。

5. **目的地守門，而且同一個 id 決定跑哪一組檢查。** 資料 repo 根目錄必須有 `.kb-data-repo`，內容要對得上
   呼叫時指定的系統 id，否則拒絕寫入。

   這條是 2026-08-19 一次真實事故換來的：tracer bullet 被指向了承載 14 天
   正式資料、且有線上網站的生產 repo，寫進去一個 schema 完全不同的檔案並
   蓋掉 index.json。**每一個訊號都說成功**——回執 exit 0 @ pushed、commit
   真的推上去了。不可改寫守衛檢查的是「檔案」，看不見「目的地」。

   有了它，publish 就從「寫到我被告知的地方」變成「**寫到承認我的地方**」。

6. **「已經寫好了」不等於「已經發布了」。** 檔案存在且內容相同時，只跳過
   寫入，rebase/push 照跑。否則上一輪卡在 push 留下的本地 commit 會永遠
   推不出去，而回執說 exit 0——又一個每個訊號都說成功的靜默失效。
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
import systems  # noqa: F401,E402  匯入即登記
from kbcore.report import run_all  # noqa: E402
from kbcore.repo import check_destination  # noqa: E402
from kbcore.result import Exit, Level  # noqa: E402
from kbcore.system import REGISTRY as SYSTEMS, get as get_system  # noqa: E402


def git(repo: Path, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=check)


def write_receipt(outbox: Path, draft_name: str, code: int, stage: str,
                  detail: str = "", commit: str = "") -> None:
    r = {
        "draft": draft_name,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "exit": code,
        "stage": stage,
        "commit": commit,
        "detail": detail,
    }
    (outbox / draft_name.replace(".draft.json", ".receipt.json")).write_text(
        json.dumps(r, ensure_ascii=False, indent=1))
    print(f"回執：exit {code} @ {stage} {detail}")


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def publish_one(draft_path: Path, repo: Path, outbox: Path, system) -> int:
    name = draft_path.name
    try:
        draft = json.loads(draft_path.read_text())
    except json.JSONDecodeError as e:
        write_receipt(outbox, name, Exit.BAD_INPUT, "parse", str(e))
        return Exit.BAD_INPUT

    # 1. 閘門。payload 怎麼組是每套系統自己的事（見 kbcore/system.py）。
    try:
        payload = system.build(draft, repo)
    except Exception as e:
        write_receipt(outbox, name, Exit.BAD_INPUT, "build-payload",
                      f"{type(e).__name__}: {e}")
        return Exit.BAD_INPUT
    results = run_all(payload, suite=system.suite)
    fails = [(c, o) for c, o in results if o.level == Level.FAIL]
    if fails:
        detail = "; ".join(f"{c.id}: {o.detail}" for c, o in fails)
        write_receipt(outbox, name, Exit.CONTENT, "verify", detail)
        return Exit.CONTENT

    date = draft["date"]
    target = repo / "data" / f"{date}.json"
    body = json.dumps(draft, ensure_ascii=False, indent=1)

    # 2. 不可改寫守衛
    #
    # 「已經寫好了」不等於「已經發布了」。上一輪可能寫完檔案、commit 完，
    # 卡在 pull/push 才失敗（exit 14）。那顆 commit 還躺在本地沒推上去。
    # 這裡如果直接 return OK，回執會說成功、草稿留在 outbox、commit 永遠
    # 不會被推——每一個訊號都說沒事，但資料根本沒上線。這就是靜默失效。
    # 所以內容相同時只跳過「寫入」，rebase/push 那一段照跑（沒東西可 commit
    # 也無所謂，push 本來就是冪等的）。
    already = False
    if target.exists():
        if target.read_text() != body:
            write_receipt(outbox, name, Exit.IMMUTABLE, "immutable",
                          f"{target.name} 已存在且內容不同 —— 改草稿沒有用，掛 errata")
            return Exit.IMMUTABLE
        already = True

    # 3. 原子寫入 ＋ index
    if not already:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, body)

    # index 是**衍生狀態**，每一輪都重建，即使日期檔沒動。
    #
    # 原本這一段被關在 `if not already:` 裡面。那會造成一個無法自我修復的洞：
    # 一旦某輪寫進了不完整的 entry，之後拿相同內容重跑並不會修好它，因為
    # 「內容相同」直接跳過整段。日期檔是不可改寫的，index 不是——它是可以、
    # 也應該被重算的。2026-08-19 首日就是這樣留下一個只有 date 與 file 的
    # entry，而隔天的跨日推理全部要靠它。
    idx_path = repo / "data" / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"days": []}
    idx["days"] = [d for d in idx.get("days", []) if d.get("date") != date]
    idx["days"].insert(0, system.index_entry(draft))
    idx["days"].sort(key=lambda d: d["date"], reverse=True)
    idx["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    idx["count"] = len(idx["days"])
    atomic_write(idx_path, json.dumps(idx, ensure_ascii=False, indent=1))

    # 4. commit → rebase → push
    git(repo, "add", "data")
    git(repo, "commit", "-m", f"data: publish {date}", check=False)
    rb = git(repo, "pull", "--rebase", check=False)
    if rb.returncode != 0:
        # **非零不等於衝突。** 沒設 upstream、網路不通、遠端不存在都會非零，
        # 把它們全部標成「rebase 衝突 —— 重跑不會好」是一個很有說服力但錯誤的
        # 診斷（2026-08-19 實測撞到）。真正的衝突會在 .git 底下留下 rebase 狀態
        # 目錄，用它來分辨。
        in_rebase = any((repo / ".git" / d).exists()
                        for d in ("rebase-merge", "rebase-apply"))
        detail = (rb.stderr or rb.stdout or "").strip()[:200]
        if in_rebase:
            git(repo, "rebase", "--abort", check=False)
            write_receipt(outbox, name, Exit.CONFLICT, "rebase",
                          f"真的衝突了，有東西寫錯地方 —— 重跑不會好：{detail}")
            return Exit.CONFLICT
        write_receipt(outbox, name, Exit.ENVIRONMENT, "rebase",
                      f"pull --rebase 失敗但不是衝突：{detail}")
        return Exit.ENVIRONMENT

    ps = git(repo, "push", check=False)
    if ps.returncode != 0:
        write_receipt(outbox, name, Exit.ENVIRONMENT, "push",
                      (ps.stderr or "").strip()[:200])
        return Exit.ENVIRONMENT

    sha = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    stage = "already-published" if already else "pushed"
    write_receipt(outbox, name, Exit.OK, stage, f"{target.name} 已發布", sha)
    draft_path.unlink()
    return Exit.OK


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return Exit.BAD_INPUT
    outbox, repo, system_id = Path(argv[1]), Path(argv[2]), argv[3]

    err = check_destination(repo, system_id)
    if err:
        print(f"DESTINATION  {err}", file=sys.stderr)
        return Exit.BAD_INPUT

    # 認不出來就停，**不要退回預設的 suite**。退回去會讓這套系統的草稿被別套的
    # 檢查驗過然後全綠 —— 每個訊號都說成功，該擋的一條都沒跑。
    system = get_system(system_id)
    if system is None:
        print(f"SYSTEM  {system_id!r} 不在登記裡（已登記：{'、'.join(sorted(SYSTEMS))}）"
              " —— 不知道該跑哪一組檢查就沒有資格發布", file=sys.stderr)
        return Exit.BAD_INPUT

    # **剛寫好的草稿先放過一輪。** 這裡每 60 秒掃一次，而寫草稿的是另一個行程；
    # 撞上一個寫到一半的檔，讀出來是 JSONDecodeError → exit 12 的回執，看起來像
    # 內容壞掉，其實只是早了兩秒。2026-08-19 首輪更糟：檔案是完整的 JSON、但還
    # 不是定稿，於是被當成成品發布，之後每一次重寫都撞不可改寫守衛。
    #
    # 正解是產出端原子寫入（寫 .tmp 再 rename），這裡的靜置只是第二層防線——
    # **兩層都要有，因為產出端是模型在跑，而模型會忘記。**
    QUIET = 10
    now = dt.datetime.now().timestamp()
    drafts, warming = [], []
    for d in sorted(outbox.glob("*.draft.json")):
        (warming if now - d.stat().st_mtime < QUIET else drafts).append(d)
    for d in warming:
        print(f"{d.name} 剛寫入不到 {QUIET} 秒，這一輪先跳過")
    if not drafts:
        print("outbox 沒有 draft —— 空輪次，不是失敗")
        return Exit.EMPTY_ROUND
    worst = Exit.OK
    for d in drafts:
        code = publish_one(d, repo, outbox, system)
        worst = code if code != Exit.OK else worst
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
