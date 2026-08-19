"""投顧知識庫。payload 要帶前一版與 anchors。

`build` 是這兩個東西的**唯一**組法：publish 用它，`tools/advisory_verify.py` 也用它。
在兩個地方各寫一份就是雙軌漂移的起點——改了一邊忘了另一邊，而且沒有任何訊號。
"""
import datetime as dt
import json
from pathlib import Path

from kbcore.system import System, register

ANCHORS = "advisory/anchors.json"
PROGRAM_ROOT = Path(__file__).resolve().parent.parent

# 每一條檢查會伸手去拿的 anchors 鍵。缺一個就在組 payload 時大聲失敗——
# **門檻取不到是設定壞了，不是資料壞了**。
#
# 這一段是 2026-08-19 寫檢查時補的：檢查引用了 anchors 沒有的兩個鍵，而 selftest
# 看不見，因為每條檢查的 fixture 自帶 anchors。**fixture 自帶設定，所以它驗不到
# 「真實設定裡有沒有這一項」**——這是 fixture 自檢的第三個盲區。
REQUIRED = ["groups", "site_total", "lengths", "fixed_structure",
            "base_card_groups", "dedup_exempt"]


class AnchorsMissing(Exception):
    pass


def load_anchors(repo: Path) -> dict:
    """資料 repo 優先，其次是程式 repo。兩邊都沒有就是設定壞了。"""
    for p in (Path(repo) / ANCHORS, PROGRAM_ROOT / ANCHORS):
        if p.exists():
            a = json.loads(p.read_text())
            missing = [k for k in REQUIRED if k not in a]
            if missing:
                raise AnchorsMissing(f"{p} 缺少檢查會用到的鍵：{'、'.join(missing)}")
            return a
    raise AnchorsMissing(f"找不到 {ANCHORS} —— 門檻沒有家，這一輪沒有資格判")


def prev_doc(data_dir: Path, date: str):
    """前一版取「小於當日的最大日期」，不是「最新的非當日」。

    歷史重跑時後者會拿到未來的那一版，跨版去重整個反過來。
    """
    if not data_dir.exists():
        return None
    days = sorted(f.stem for f in data_dir.glob("*.json")
                  if f.stem != "index" and f.stem < date)
    return json.loads((data_dir / f"{days[-1]}.json").read_text()) if days else None


def build(draft, repo: Path):
    return {
        "doc": draft,
        "prev": prev_doc(Path(repo) / "data", draft.get("date", "")),
        "anchors": load_anchors(repo),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


register(System(
    id="advisory-knowledge-hub",
    suite="advisory",
    build=build,
))
