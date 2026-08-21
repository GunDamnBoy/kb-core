"""這一套所有路徑的**唯一的家**。

## 為什麼需要它

每支程式各自寫 `~/broker-research/...` 當預設，看起來很一致 ——
**但 `~` 在不同的執行環境展開成不同的地方**：

| 誰在跑 | `~` 是什麼 | 對不對 |
|---|---|---|
| Mac 上的 launchd（publish） | `/Users/macmini` | ✅ |
| Cowork 工作階段的 device bash | 那個階段自己的沙箱家目錄 | ❌ **而且是安靜地錯** |

2026-08-21 這件事咬了三次，每次的樣子都不一樣、每次都很有說服力：

1. `publish` 的閘門紅了而 `research_verify` 全綠 —— 兩邊讀到不同的拷貝。
2. `extract.py` 回報「18 份抽取完成」，寫進沙箱，掛載那邊一份都沒動。
3. `build_index.py` 說「空輪次，不是失敗」—— 而 inbox 裡有 18 份。

**第 2 和第 3 是最糟的形狀**：它們的輸出讀起來完全正常。
「18 份抽好了」與「18 份抽好了、但在沒有人會去看的地方」長得一模一樣。

## 規則

**根目錄由 `BROKER_RESEARCH_ROOT` 決定**，沒設才退回 `~/broker-research`。
排程的 plist 明寫絕對路徑；Cowork 階段照 `RUN-PROMPT` 明寫掛載路徑。
**兩邊都不靠 `~` 猜。**
"""
import os

ENV = "BROKER_RESEARCH_ROOT"


def root() -> str:
    return os.path.expanduser(os.environ.get(ENV, "~/broker-research"))


def under(*parts: str) -> str:
    return os.path.join(root(), *parts)


def inbox() -> str:
    return under("inbox")


def extracted() -> str:
    return under("extracted")


def digest() -> str:
    return under("digest")
