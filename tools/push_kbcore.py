#!/usr/bin/env python3
"""把 kb-core 自己推上遠端。跑在 Mac 上，由 launchd 觸發。

用法：push_kbcore.py <kb-core 路徑>

## 為什麼需要這一支

2026-08-21 發現：`kb-core` 有 remote，但八個 launchd 工作裡**沒有任何一支推它**。
重建前是 `com.kenny.dashpush`（掃全 repo add+commit+push）順手帶的，
08-20 重建時它退場，而「誰來推 kb-core」沒有交接給任何人。
同一天發現的 `charts/` 沒被推是同一個病的另一個病灶。

**這一支跟 `publish.py` 不是同一類東西，不要把它們寫成一個。**

| | `publish.py` | 這一支 |
|---|---|---|
| 推的是 | 機器產生、發布後不可改寫的 `data/` | **人與模型在改的原始碼** |
| 閘門 | 內容檢查（跑那一套系統的 suite） | 語法 ＋ 檢查自檢（**這個 repo 就是檢查機制本身**） |
| 觸發 | outbox 有草稿 | 工作區靜置且有未推的東西 |
| 落後 origin 時 | `pull --rebase` 然後續推 | **停下來報告，不自動 rebase** |

最後一列是刻意的。kb-core 是另外三套排程**正在執行中**的程式碼；
在它們跑的同時 rebase 這個工作區，等於讓 `import checks` 有機會讀到一個
寫到一半的檔案。單一寫入者的 repo 落後 origin 本來就代表「有人在別處動過」，
那是一個需要人看的狀況，不是一個該自動化掉的狀況。

## 三道閘門，順序有意義

1. **這是不是 kb-core** —— 認路標（`tools/publish.py`、`kbcore/system.py`、
   `checks/chart.py`）。`publish.py` 用 `.kb-data-repo` 做目的地守門，
   理由一樣：**寫到承認我的地方，不是寫到我被告知的地方。**

2. **工作區靜置** —— 最近一次檔案修改要超過 `QUIET_MINUTES`。
   模型改到一半、人打字打到一半的狀態不該被 commit。
   `publish.py` 的 10 秒靜置是同一個機制的小號版本。

3. **語法與檢查自檢全綠** —— `py_compile` 全部 `.py`，再跑 `report.selftest()`。
   **這一條比前兩條重要**：推壞掉的 `checks/` 上去，等於讓三套系統的閘門
   同時失效，而它們的回執還是會說成功。一個推不上去的 repo 只是不方便，
   一個推上去的壞閘門是靜默失效。

## 回執

寫在 `<kb-core>/.push-receipt.json`（`.gitignore` 內，不進版控）。
**「沒有回執」與「回執說失敗」是兩件不同的事**——前者代表這一支根本沒跑。
`publish.py` 那條註解逐字適用。
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.result import Exit  # noqa: E402

QUIET_MINUTES = 5
LANDMARKS = ("tools/publish.py", "kbcore/system.py", "checks/chart.py")
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
RECEIPT = ".push-receipt.json"


def git(repo: Path, *args, check=False):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=check)


def receipt(repo: Path, code: int, stage: str, detail: str = "", commit: str = "") -> int:
    r = {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "exit": code,
        "stage": stage,
        "commit": commit,
        "detail": detail,
    }
    (repo / RECEIPT).write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(f"回執：exit {code} @ {stage} {detail}")
    return code


def newest_mtime(repo: Path) -> float:
    """工作區裡最後一次被碰過的時間。`.git` 與快取不算——
    **git 自己寫 `.git` 底下的檔，把它算進來會讓靜置永遠不成立。**"""
    newest = 0.0
    for base, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f == RECEIPT:
                continue          # 自己寫的回執不算「有人在改」
            try:
                newest = max(newest, os.stat(os.path.join(base, f)).st_mtime)
            except OSError:
                pass
    return newest


def gate_selftest(repo: Path) -> str:
    """語法 ＋ 檢查自檢。回傳空字串＝通過，否則是要寫進回執的理由。

    **在子行程裡跑**，不是 import 進來跑：這支腳本自己就住在被檢查的 repo 裡，
    當下的直譯器早就把舊版本載進記憶體了，import 驗不到剛剛改壞的那一份。
    """
    pys = [str(p) for p in repo.rglob("*.py")
           if not any(part in SKIP_DIRS for part in p.parts)]
    r = subprocess.run([sys.executable, "-m", "py_compile", *pys],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"py_compile 失敗：{(r.stderr or '').strip()[:300]}"

    code = ("import sys; sys.path.insert(0, %r)\n"
            "import checks, systems\n"
            "from kbcore.report import selftest\n"
            "d = selftest()\n"
            "print('\\n'.join(d))\n"
            "sys.exit(1 if d else 0)\n") % str(repo)
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, cwd=str(repo))
    if r.returncode != 0:
        why = (r.stdout or r.stderr or "").strip()[:300]
        return f"檢查自檢有失敗的條目：{why}"
    return ""


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return Exit.BAD_INPUT
    repo = Path(argv[1]).expanduser()

    # 閘門 1：認路標
    missing = [m for m in LANDMARKS if not (repo / m).exists()]
    if missing or not (repo / ".git").exists():
        print(f"{repo} 不像是 kb-core（缺 {missing or '.git'}）—— "
              "**寫到承認我的地方，不是寫到我被告知的地方**", file=sys.stderr)
        return Exit.BAD_INPUT

    # 有沒有事情要做。**兩個問題要分開問**：
    #   (a) 工作區有沒有未提交的東西
    #   (b) 本機有沒有領先 origin（上一輪 commit 完卡在 push 的情形）
    # 只問 (a) 會讓一顆推不出去的 commit 永遠留在本機，而每一輪都說「沒事做」。
    # 這就是 publish.py 那條「已經寫好了不等於已經發布了」的同一個坑。
    dirty = bool(git(repo, "status", "--porcelain").stdout.strip())
    ahead = git(repo, "rev-list", "--count", "@{u}..HEAD").stdout.strip() or "0"
    try:
        ahead_n = int(ahead)
    except ValueError:
        ahead_n = 0            # 沒設 upstream，交給後面的 push 去報
    if not dirty and ahead_n == 0:
        print("kb-core 乾淨且未領先 origin —— 空輪次，不是失敗")
        return Exit.EMPTY_ROUND

    # 閘門 2：靜置
    if dirty:
        idle = (dt.datetime.now().timestamp() - newest_mtime(repo)) / 60
        if idle < QUIET_MINUTES:
            print(f"工作區 {idle:.1f} 分鐘前還被動過（需靜置 {QUIET_MINUTES} 分鐘）"
                  " —— 這一輪先跳過，不 commit 改到一半的東西")
            return Exit.EMPTY_ROUND

    # 閘門 3：語法與檢查自檢
    why = gate_selftest(repo)
    if why:
        return receipt(repo, Exit.CONTENT, "gate",
                       f"{why} —— **不推**。推壞掉的 checks/ 上去，"
                       "三套系統的閘門會同時失效而回執照樣說成功")

    if dirty:
        git(repo, "add", "-A")
        stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        # 訊息標 auto，讓人工 commit 在歷史裡分得出來。
        git(repo, "commit", "-m", f"chore(auto): kb-core 快照 {stamp}")

    ps = git(repo, "push")
    if ps.returncode != 0:
        err = (ps.stderr or ps.stdout or "").strip()
        # **先 fetch 再數。** 不 fetch 的話 `@{u}` 指的是本機那份過期的
        # remote-tracking ref，落後幾顆一律算成 0 —— 一個看起來很具體、
        # 而且永遠是 0 的數字，比不給數字更糟。fetch 只動 .git 底下的 ref，
        # 不碰工作區，所以它不違反「不自動 rebase」那條。
        git(repo, "fetch", "--quiet")
        behind = git(repo, "rev-list", "--count", "HEAD..@{u}").stdout.strip()
        if "non-fast-forward" in err or "rejected" in err or (behind or "0") != "0":
            return receipt(repo, Exit.CONFLICT, "diverged",
                           f"本機落後或分岔 origin（落後 {behind or '?'} 顆）—— "
                           "**這一支刻意不自動 rebase**：另外三套排程正在跑這份程式碼，"
                           f"在它們跑的時候改寫工作區會讓 import 讀到半成品。要人來看：{err[:200]}")
        return receipt(repo, Exit.ENVIRONMENT, "push", err[:200])

    sha = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return receipt(repo, Exit.OK, "pushed", "kb-core 已推上 origin", sha)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
