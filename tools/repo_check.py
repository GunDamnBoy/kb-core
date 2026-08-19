#!/usr/bin/env python3
"""repo lint —— 跑在 push／PR 上，抓的是這個 repo 本身的設定錯誤。

用法：repo_check.py <repo 路徑>

跟哨兵分開，因為它們回答不同的問題：哨兵問「這套系統還活著嗎」（每天），
lint 問「有人剛剛改壞了什麼嗎」（每次改動）。把 lint 塞進每日哨兵，等於要等
最多 24 小時才知道設定寫錯了。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
from checks.repo import CHARS_PER_TOKEN  # noqa: E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

BUDGET_RE = re.compile(r"^\s*tokens:\s*(\d+)", re.M)
SOURCE_RE = re.compile(r'^\s*source:\s*"?(.+?)"?\s*$', re.M)


def read_briefs(repo: Path):
    out = []
    for f in sorted(repo.rglob("BRIEF.md")):
        text = f.read_text(errors="replace")
        head = text[:2000]
        m, sm = BUDGET_RE.search(head), SOURCE_RE.search(head)
        out.append({
            "path": str(f.relative_to(repo)),
            "budget": int(m.group(1)) if m else None,
            "budget_source": sm.group(1).strip() if sm else "",
            "est_tokens": round(len(text) / CHARS_PER_TOKEN),
        })
    return out


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return Exit.BAD_INPUT
    repo = Path(argv[1])
    if not (repo / ".git").exists():
        print(f"{repo} 不是一個 git repo", file=sys.stderr)
        return Exit.BAD_INPUT

    wf_dir = repo / ".github" / "workflows"
    payload = {
        "workflows": [{"path": str(f.relative_to(repo)),
                       "text": f.read_text(errors="replace")}
                      for f in sorted(wf_dir.glob("*.y*ml"))] if wf_dir.exists() else [],
        "briefs": read_briefs(repo),
    }
    print(f"掃到 {len(payload['workflows'])} 份 workflow、"
          f"{len(payload['briefs'])} 份 BRIEF.md")
    return report(run_all(payload, suite="repo"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
