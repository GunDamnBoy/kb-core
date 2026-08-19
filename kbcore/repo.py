"""資料 repo 的身分辨識——「我現在站在哪裡」。

2026-08-19 的事故教的：不可改寫守衛檢查的維度是**檔案**，它從設計上就看不見
「我站在哪個 repo」。所有破壞性動作都要問同一個問題——我驗證的是**物件**，
還是**我所在的位置**？前者永遠答不出後者。

這段刻意放在 kbcore 而不是 publish.py 裡：publish 要用它，哨兵的看門狗也要用。
守衛複製成兩份就是**雙軌漂移**的起點——改了一邊忘了另一邊，而且沒有任何訊號。
"""
from pathlib import Path

MARKER = ".kb-data-repo"


def check_destination(repo: Path, system_id: str) -> str:
    """回傳錯誤訊息；空字串表示通過。"""
    marker = Path(repo) / MARKER
    if not marker.exists():
        return f"{repo} 沒有 {MARKER} —— 它不是一個資料 repo，拒絕動作"
    got = marker.read_text().strip()
    if got != system_id:
        return f"{MARKER} 是 {got!r}，但呼叫指定的是 {system_id!r} —— 目的地不符，拒絕動作"
    return ""
