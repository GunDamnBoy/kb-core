"""每日五圖的工具共用的 repo 定位。

## 為什麼不從 `__file__` 推

舊制每一支工具都寫 `REPO = dirname(dirname(abspath(__file__)))` ——
程式住在資料 repo 的 `tools/` 底下時，那推得出正確答案。

**但那個預設值在搬家之後仍然解析得出一個看起來合法的路徑**（`kb-core/`），
所以不會報錯，只會把資料寫錯地方、或讀到一個空的 `data/`。
2026-08-20 把工具搬進 kb-core 時，這是唯一真正的障礙。

改成：**明講，或大聲失敗**。沒有 `CHART_REPO` 也沒有傳參數，就停下來，
而不是猜一個。這條的代價是每個呼叫點都要寫路徑；換來的是搬家不會靜默地把東西寫到別處。
"""
import os
import sys


def repo(explicit: str = "") -> str:
    p = explicit or os.environ.get("CHART_REPO") or ""
    if not p:
        sys.exit("找不到資料 repo —— 設 CHART_REPO 或明確傳入路徑。"
                 "**這裡刻意不猜**：從 __file__ 推導的預設值在程式搬家之後"
                 "仍然解析得出一個合法路徑，於是資料會被安靜地寫到別的地方。")
    p = os.path.expanduser(p)
    if not os.path.isdir(os.path.join(p, "data")):
        sys.exit(f"{p} 底下沒有 data/ —— 這不像是每日五圖的資料 repo")
    return p
