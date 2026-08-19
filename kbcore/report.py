"""跑檢查、印報告、決定退出碼。

最重要的一段是 `_print_blind_spots`：**全綠時一定要把所有 blind_to 印出來。**
全綠的那一刻正是最危險的時刻——「一條永遠會 PASS 的檢查比沒有這條檢查更糟，
它會讓人以為已經驗過」。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .check import REGISTRY, Check, Outcome
from .result import Exit, Level

SKIPPED_LIMIT = 3  # SKIPPED 超過這個數量就視同 FAIL


def run_all(payload: Any) -> List[Tuple[Check, Outcome]]:
    return [(c, c.run(payload)) for c in REGISTRY.values()]


def selftest() -> List[str]:
    """每條檢查都必須被自己的 fixture 觸發。回傳失敗的 id 清單。"""
    dead = []
    for c in REGISTRY.values():
        try:
            outcome = c.run(c.fixture)
        except Exception as e:  # fixture 讓它爆掉也算被觸發
            continue
        if outcome.level == Level.PASS:
            dead.append(c.id)
    return dead


def check_lock(lock_path: Path) -> Tuple[List[str], List[str]]:
    """項目數只增不減。回傳 (消失的 id, 新增的 id)。"""
    current = set(REGISTRY)
    known = set()
    if lock_path.exists():
        known = {l.strip() for l in lock_path.read_text().splitlines() if l.strip()}
    return sorted(known - current), sorted(current - known)


def _print_blind_spots() -> None:
    seen = []
    for c in REGISTRY.values():
        for b in c.blind_to:
            if b not in seen:
                seen.append(b)
    print(f"\n本輪檢查看不到的形態（blind_to 彙總，{len(seen)} 項）")
    for b in seen:
        print(f"  · {b}")


def report(results: List[Tuple[Check, Outcome]]) -> int:
    counts = {lv: 0 for lv in Level}
    for _, o in results:
        counts[o.level] += 1

    for lv in (Level.FAIL, Level.WARN, Level.SKIPPED):
        rows = [(c, o) for c, o in results if o.level == lv]
        if not rows:
            continue
        print(f"\n{lv.value}（{len(rows)}）")
        for c, o in rows:
            print(f"  {c.id:<28} {o.detail}")

    envs = [(c, o) for c, o in results if o.level == Level.ENV]
    if envs:
        print(f"\nENV（{len(envs)}，不計數、不影響退出碼）")
        for c, o in envs:
            print(f"  {c.id:<28} {o.detail}")

    print(
        f"\n{counts[Level.PASS]} PASS · {counts[Level.WARN]} WARN · "
        f"{counts[Level.FAIL]} FAIL · {counts[Level.SKIPPED]} SKIPPED · "
        f"{counts[Level.ENV]} ENV"
    )

    _print_blind_spots()

    if counts[Level.FAIL]:
        return Exit.CONTENT
    if counts[Level.SKIPPED] > SKIPPED_LIMIT:
        print(f"\nSKIPPED {counts[Level.SKIPPED]} 項超過上限 {SKIPPED_LIMIT} —— 視同 FAIL")
        return Exit.CONTENT
    return Exit.OK
