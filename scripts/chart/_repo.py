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

# ── kb-core 自己的根目錄 ────────────────────────────────────────────
# **這裡從 `__file__` 推是對的，上面那段警告不適用。** 兩者是不同的東西：
# 資料 repo 的位置是**執行時的選擇**（同一份程式可以指向不同的 repo，
# 猜錯的樣子是「寫到別的目錄而且看起來成功」），而 kb-core 的根目錄是
# **這個模組自己所在的位置**——它不可能指到別份程式碼，推錯會 ImportError。
#
# 加它是為了讓 `scripts/chart/*` 能 `from kbcore.repo import ...`：
# 日檔的序列化格式與 publish 共用一個家（2026-08-29，見 `kbcore/repo.day_json`）。
_KB_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _KB_CORE not in sys.path:
    sys.path.insert(0, _KB_CORE)


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
