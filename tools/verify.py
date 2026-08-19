#!/usr/bin/env python3
"""verify —— 底盤的檢查器進入點。

用法：
  verify.py --selftest              跑 fixture 自檢 ＋ checks.lock 對帳
  verify.py --write-lock            把目前的 check id 集合寫進 checks.lock
  verify.py <payload.json>          對一份 payload 跑全部檢查

退出碼見 kbcore/result.py 的 Exit。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402  匯入即註冊
import systems  # noqa: F401,E402  匯入即登記
from kbcore.check import REGISTRY  # noqa: E402
from kbcore.system import REGISTRY as SYSTEMS  # noqa: E402
from kbcore.report import check_lock, report, run_all, selftest  # noqa: E402
from kbcore.result import Exit  # noqa: E402

LOCK = ROOT / "checks.lock"


def do_selftest() -> int:
    dead = selftest()
    gone, added = check_lock(LOCK)

    print(f"已註冊檢查：{len(REGISTRY)} 條、系統 {len(SYSTEMS)} 套")

    if dead:
        print("\n以下檢查沒有被自己的 fixture 觸發 —— 它們是永遠會 PASS 的檢查：")
        for d in dead:
            print(f"  {d}")
    if gone:
        print("\ncheck id 消失（項目數只增不減）：")
        for g in gone:
            print(f"  {g}")
    if added:
        print("\n新增的 check id（跑 --write-lock 收進 lock）：")
        for a in added:
            print(f"  {a}")

    # 登記了系統、卻沒有對應的檢查 —— 那套系統會在 publish 當下才爆，
    # 而那時候草稿已經在 outbox 裡了。在 CI 就擋下來。
    suites = {c.suite for c in REGISTRY.values()}
    empty = sorted(f"{sid}（suite={sy.suite}）"
                   for sid, sy in SYSTEMS.items() if sy.suite not in suites)
    if empty:
        print("\n以下系統登記的 suite 一條檢查都沒有：")
        for e in empty:
            print(f"  {e}")

    if dead or gone or empty:
        return Exit.CONTENT
    print("\nselftest OK")
    return Exit.OK


def do_write_lock() -> int:
    LOCK.write_text("\n".join(sorted(REGISTRY)) + "\n")
    print(f"寫入 {LOCK}（{len(REGISTRY)} 條）")
    return Exit.OK


def do_verify(path: Path) -> int:
    if not path.exists():
        print(f"找不到 payload：{path}", file=sys.stderr)
        return Exit.BAD_INPUT
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"payload 不是合法 JSON：{e}", file=sys.stderr)
        return Exit.BAD_INPUT
    if not isinstance(payload, dict):
        print("payload 頂層必須是物件", file=sys.stderr)
        return Exit.BAD_INPUT
    if payload.get("empty_round"):
        print("空輪次 —— 不是失敗，是設計")
        return Exit.EMPTY_ROUND
    return report(run_all(payload))


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return Exit.BAD_INPUT
    arg = argv[1]
    if arg == "--selftest":
        return do_selftest()
    if arg == "--write-lock":
        return do_write_lock()
    return do_verify(Path(arg))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
