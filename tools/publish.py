#!/usr/bin/env python3
"""publish —— 唯一的發布路徑。跑在 Mac 上，由 launchd 觸發。

用法：publish.py <outbox> <資料 repo> <系統 id>

流程：目的地守門 → 掃 outbox → verify（閘門）→ 不可改寫守衛 → 原子寫入
      data/ → 更新 index → add（依系統宣告）→ 對帳 → pull --rebase → commit
      → push → 寫回執

七條刻意的設計：

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

7. **要 add 哪些路徑由系統宣告，而且宣告完要對帳。** publish 不知道任何一套
   系統產出什麼形狀的東西——`data/` 是三套裡兩套的答案，不是通則。
   宣告在 `System.staged_paths`；對帳在步驟 4b，問的是「這些路徑底下還有沒有
   沒進版控的檔」。**宣告與量測分開**，因為 2026-08-21 那次的每一個訊號
   （回執 exit 0、18 條檢查全綠、commit 推上去了）都說成功，而 charts/ 從來
   沒被 add 過——`chart.png_present` 讀的是本機檔案系統，看不見遠端。
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


def dirty_outside(porcelain: str, paths) -> list:
    """`git status --porcelain` 的輸出裡，**不在 `paths` 底下**的那些路徑。

    抽成純函式的唯一理由是它驗得動 —— 解析是這一段唯一會寫錯的地方，
    而跑 git 不是。呼叫端見 publish() 的 4a。

    porcelain 的格式是兩個狀態字元 ＋ 一個空白 ＋ 路徑，所以路徑從第 4 個字元
    開始。兩個要小心的形態：改名是 `R  舊 -> 新`（取新的那一邊，舊的已經不存在了），
    含空白或非 ASCII 的路徑會被 git 包成 `"..."`（引號不是路徑的一部分）。

    **`staged_paths` 裡可以是檔案，不只是目錄**，所以比對要同時認「等於」與
    「在它底下」。初版只寫了後者（`p.startswith(q + "/")`），於是投顧的
    `["data", "index.html"]` 裡那個 `index.html` **被判成不歸 publish 管** ——
    一個系統明文宣告要推的檔，被擋在推它的那一步之前，而且是每 60 秒一次。
    同一版的註解還宣稱「不可能讓事情比現況更糟」：那句話對目錄型的
    `staged_paths` 成立，對檔案型的**不成立**（改動前 `git add -- index.html`
    會把它 commit 掉、rebase 順利通過）。**驗的時候只測了目錄型的多路徑系統，
    而唯一含檔案的那一套沒被測到 —— 會壞的正好是沒測的那一個。**
    """
    out = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        p = line[3:].split(" -> ")[-1].strip().strip('"')
        if not p:
            continue
        q = p.rstrip("/")
        if not any(q == own or q.startswith(own + "/")
                   for own in (s.rstrip("/") for s in paths)):
            out.append(p)
    return out


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
    # **允不允許改寫是每套系統自己的事**（見 `kbcore/system.py` 的 `republish_rule`）。
    # 這裡原本硬寫「內容不同就擋」—— 對日頻是對的，對週頻不是：
    # 週摘依報告自己的日期分期，而報告不會在週末停止到達。
    # 這是同一道接縫漏掉的第四個維度（前三個是 index_entry／index_meta／staged_paths）。
    already = False
    if target.exists():
        if target.read_text() != body:
            try:
                old_doc = json.loads(target.read_text())
            except json.JSONDecodeError:
                old_doc = {}
            why = system.republish_rule(old_doc, draft)
            if why:
                write_receipt(outbox, name, Exit.IMMUTABLE, "immutable",
                              f"{target.name} {why}")
                return Exit.IMMUTABLE
            print(f"改寫 {target.name} —— 系統的 republish_rule 判定這是允許的變更")
        else:
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
    # 頂層欄位由系統決定，publish 不知道任何一套系統的形狀。
    # 硬寫在這裡的代價已經付過兩次了（index entry 的欄位、updatedLabel）。
    idx.update(system.index_meta(draft))
    idx["count"] = len(idx["days"])
    atomic_write(idx_path, json.dumps(idx, ensure_ascii=False, indent=1))

    # 4. commit → rebase → push
    #
    # **要 add 哪些路徑是每套系統自己的事**（見 kbcore/system.py 的 staged_paths）。
    # 這裡原本硬寫 `add "data"` —— 對投顧與 podcast 是對的，對每日五圖不是，
    # 它每天還有 `charts/<date>/*.png|svg` 要推，而那是 House View 的 pptx
    # 直接吃的路徑。2026-08-21 抓到：那些檔從 08-20 重建之後就沒有人推過。
    paths = system.staged_paths(draft, repo)

    # 4a. rebase 之前先確認工作區乾淨 —— **而且要在 add／commit 之前問**。
    #
    # `git pull --rebase` 要求工作區沒有未提交的變更，而上面那個 `staged_paths`
    # 只涵蓋各系統自己那幾條路徑（podcast 是 `data`）。**repo 根目錄那些已被追蹤、
    # 被改過、沒被提交的檔案，publish 永遠 stage 不到，也永遠 commit 不掉**，
    # 於是 rebase 每一輪都倒在同一個地方。
    #
    # 2026-08-24 實際發生過：08-23 一場維護改了 README.md、AGENT_BRIEF.md、
    # MAINTENANCE.md 沒有提交，隔天 03:32 到 06:43 每 60 秒重試一次、
    # **回執連續 191 輪都是 `exit 14 @ rebase`**，而每一輪都先成功 commit 了一次
    # data，累積 188 筆推不出去的本地 commit（其中 187 筆只改了 index.json
    # 的一個時間戳）。**191 是輪數、188 是 commit 數，兩個數字都量過，不要混用。**
    #
    # 三個決定，每個都有理由：
    #
    #   - **放在 add／commit 之前**，不是之後。放之後照樣會每輪長一筆垃圾 commit ——
    #     退出碼換了、堆積沒停，因為 launchd 不會因為某個碼就不再排下一輪。
    #   - **用 CONFLICT(15) 不是 ENVIRONMENT(14)。** result.py 區分這兩個碼的軸線
    #     是「重跑會不會好」：14 是可能會好，而**這一種重跑永遠不會好**。
    #     碼寫錯的代價是實的 —— 流程正本照 14 的語意寫著「會自己重試」，
    #     於是那天沒有人有理由介入。不用 BAD_INPUT(12) 是因為草稿本身沒有問題，
    #     壞掉的是 repo 的狀態；push_kbcore.py 的 "diverged" 已經是同一個用法。
    #   - **不嘗試代為 stash 或提交。** 那些是別人做到一半的工作，
    #     publish 不知道它們完成了沒有。擋下來讓人看，比替人決定安全。
    #
    # **這一條只在比對正確時才「不會讓事情更糟」，而初版的比對是錯的。**
    # 原本想寫的是：它擋下來的每一種狀態，原本都會在三行之後的 rebase 倒下，
    # 所以它只是把無限迴圈換成一次具名的停止。那句話對**目錄型**的
    # `staged_paths` 成立 —— 但初版把 `staged_paths` 一律當目錄，於是投顧的
    # `index.html`（檔案）被判成外人，而它原本會被下一行 add 掉、順利推上去。
    # **同一場的驗證只測了目錄型的多路徑系統，漏掉唯一含檔案的那一套。**
    # 修正見 dirty_outside() 的 docstring。教訓不是「要多測幾個案例」，是
    # **宣稱「不可能更糟」之前，先去數有幾種輸入形狀，而不是數自己測了幾個**。
    #
    # **`rstrip("\n")` 不是 `strip()`，而這個差別擋掉一整天的發布。**
    # porcelain 的每一行是「兩個狀態字元 ＋ 一個空白 ＋ 路徑」，
    # 而**只在工作區改動、沒 add** 的那一種第一個字元就是空白（`" M path"`）。
    # `.strip()` 會把整份輸出最前面那個空白吃掉，於是**第一行**變成 `"M path"`，
    # `dirty_outside()` 的 `line[3:]` 跟著位移一格 —— `data/index.json` 被讀成
    # `ata/index.json`，對不上 `paths` 裡的 `data`，於是 publish 把**自己剛寫的檔**
    # 判成外人，回 CONFLICT(15)。2026-08-24 實測：09:44 起每 60 秒一次，
    # 回執寫著「repo 有 1 個未提交的變更……：ata/index.json」。
    #
    # **它藏住的方式有三層。**
    #   ① 只有第一行會壞 —— 第二行以後的空白還在，所以 `index.html` 那種
    #      同時髒掉的檔照樣通過，錯誤看起來像「只有一個檔有問題」而不是解析壞了。
    #   ② `dirty_outside()` 是純函式、fixture 餵的是**沒被 strip 過**的字串，
    #      所以它自己的測試永遠是綠的 —— 壞的是呼叫端，而呼叫端沒有測試。
    #   ③ 這道護欄的錯誤訊息長得像真的：它說的路徑「確實不在 paths 底下」，
    #      因為那個路徑是它自己切壞的。**訊息可信，內容是假的。**
    #
    # 空行由 `dirty_outside()` 自己的 `if not line.strip(): continue` 處理，
    # 這裡只需要把尾端換行去掉；輸出全空時 `rstrip` 回空字串，`if dirty` 照樣是假。
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no",
                check=False).stdout.rstrip("\n")
    if dirty:
        outside = dirty_outside(dirty, paths)
        if outside:
            n = len(outside)
            head = "、".join(outside[:3])
            write_receipt(outbox, name, Exit.CONFLICT, "worktree-dirty",
                          f"repo 有 {n} 個未提交的變更不在 publish 負責的路徑"
                          f"（{'、'.join(paths)}）底下：{head}{' …' if n > 3 else ''}"
                          " —— rebase 會被它們擋住，而 publish stage 不到它們，"
                          "**重跑不會好**。請人提交或 stash 之後下一輪就會自己過。")
            return Exit.CONFLICT

    git(repo, "add", "--", *paths)
    git(repo, "commit", "-m", f"data: publish {date}", check=False)

    # 4b. 宣告與事實對帳。
    #
    # **這一段是量測，不是自述。** 上面那行 add 失敗（路徑不存在、權限、
    # 被 .gitignore 吃掉）不會拋錯，commit 也照樣回 0（沒東西可 commit 是允許的），
    # 於是宣告了、跑完了、回執寫 exit 0 —— 而檔案在遠端不存在。
    # 這正是 2026-08-21 的形狀，只是當時連宣告都沒有。
    #
    # 問法是「這些路徑底下還有沒有沒進版控的檔」，不是「add 有沒有回 0」——
    # 前者問的是結果，後者問的是我有沒有照做。
    leftover = git(repo, "ls-files", "--others", "--exclude-standard", "--", *paths,
                   check=False).stdout.strip()
    if leftover:
        n = len(leftover.splitlines())
        head = "、".join(leftover.splitlines()[:3])
        write_receipt(outbox, name, Exit.ENVIRONMENT, "static-outputs",
                      f"宣告要推的路徑（{'、'.join(paths)}）底下還有 {n} 個檔沒進版控："
                      f"{head}{' …' if n > 3 else ''} —— **不寫 exit 0**，"
                      "下一輪會重試；連續幾輪都這樣就是 add 進不去，要人看")
        return Exit.ENVIRONMENT
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
