"""檢查是一個帶 metadata 的物件，不是一個函式。

`covers` 說它看得見什麼，`blind_to` 說它**明確看不見**什麼——後者是整份契約的
核心。舊系統四支檢查器加起來零個邊界聲明，而規格明訂「每個檢查都要聲明自己的
邊界」。只寫在文件裡的規則會漂移，所以這裡把它變成必填欄位。
"""
from dataclasses import dataclass, field
from typing import Any, Callable, List

from .result import Level


@dataclass(frozen=True)
class Outcome:
    level: Level
    detail: str = ""


def ok(detail: str = "") -> Outcome:
    return Outcome(Level.PASS, detail)


def warn(detail: str) -> Outcome:
    return Outcome(Level.WARN, detail)


def fail(detail: str) -> Outcome:
    return Outcome(Level.FAIL, detail)


def skipped(detail: str) -> Outcome:
    """檢查跑不了。不是 PASS。"""
    return Outcome(Level.SKIPPED, detail)


def env(detail: str) -> Outcome:
    """環境狀態，不是資料故障。不計數。"""
    return Outcome(Level.ENV, detail)


@dataclass
class Check:
    id: str
    covers: str
    blind_to: List[str]
    run: Callable[[Any], Outcome]
    fixture: Any
    """一個**一定會讓這條檢查回傳非 PASS** 的樣本。

    底盤啟動時會拿它跑一次自檢：不會被自己 fixture 觸發的檢查 ＝ 永遠會 PASS
    的檢查 → FAIL。這把「一條永遠會 PASS 的檢查比沒有這條檢查更糟」從紀律變成
    機制。舊系統修過至少五處這類靜默，每一處都是「寫了但從沒被觸發過」。
    """

    suite: str = "draft"
    """這條檢查看的是哪一種 payload。

    草稿、哨兵、看門狗吃的東西形狀完全不同，但**檢查的契約只有一份**——
    covers／blind_to／fixture／自檢／lock 全部共用。分組只是讓 run_all 跑對得上
    的那一組，不是長出第二套機制。

    替代方案是「每個 suite 一個 REGISTRY」，那會讓自檢與 lock 也分裂成三份，
    於是「有沒有哪條檢查永遠 PASS」要問三次——**分裂的機制就是會漂移的機制**。
    """


REGISTRY: "dict[str, Check]" = {}


def register(check: Check) -> Check:
    if check.id in REGISTRY:
        raise ValueError(f"重複的 check id：{check.id}")
    if not check.blind_to:
        raise ValueError(f"{check.id} 沒有宣告 blind_to —— 邊界聲明是必填的")
    REGISTRY[check.id] = check
    return check
