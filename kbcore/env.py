"""環境事實 —— 底盤依賴的外部二進位檔，以及 launchd 看得到的 PATH。

## 為什麼這一檔存在

2026-08-19：`podfetch` 的規格寫著「主程式**零外部相依**，只用 Python 標準函式庫」。
那句話對 Python 套件是真的，但它**漏掉了一個外部二進位檔**（ffmpeg）。
換機建置時照著環境事實清單走，於是 ffmpeg 沒被裝 —— 而 podfetch 找不到它時
**不會報錯，直接改用內建切檔**，連 log 都沒有。

**「零依賴」要標明是哪一種依賴。** 這一檔就是那份標明。

## 為什麼要用 launchd 的 PATH 解析

`which ffmpeg` 在你的互動 shell 裡會成功（因為 `.zshrc` 把 Homebrew 加進 PATH），
但 **launchd 的 PATH 只有四個系統目錄**（2026-08-19 實測）。

所以「在終端機測得到」不代表「排程跑得到」——這是本系統反覆撞到的那一類：
**環境的限制被當成世界的事實。** 檢查一律對排程實際看得到的 PATH 解析，
不是對當下這個 process 的 PATH。
"""
import os
from pathlib import Path

# 2026-08-19 實測值（工單 19）。改 plist 的 EnvironmentVariables 時，這裡要跟著改。
LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

# 外部二進位檔 → 找不到會怎樣。
REQUIRED_BINARIES = {
    "ffmpeg": (
        "podfetch 切 20 分鐘音檔段。**找不到時不會報錯**，直接改用內建切檔且無 log；"
        "而歷史的完整度基準是在有 ffmpeg 的條件下校準的，換切段器等於換量測基準。"
    ),
    "git": "publish 與看門狗要推送與比對。",
}

# **哪一支排程需要哪些。** 第一版寫成「每支 plist 都查全部」，理由寫得像美德
# （「少宣告一個依賴的代價遠大於多查一個」），實際後果是 kbpublish 與 kbwatch
# 會永遠因為找不到 ffmpeg 而 FAIL —— 而它們根本不用 ffmpeg。
#
# **那是一個會固定響的警報，也就是雜訊。** 需求要逐支宣告，不是一視同仁。
REQUIRED_BY_LABEL = {
    "com.kenny.podfetch":  [],
    "com.kenny.kbpublish": ["git"],
    "com.kenny.kbwatch":   ["git"],
}

# **有比較好，沒有也能跑。** 缺席是 WARN 不是 FAIL —— 把降級判成失敗，
# 跟把失敗判成正常一樣糟：前者製造會固定響的警報，後者製造靜默。
#
# ffmpeg 的定位是 2026-08-19 讀了 podfetch 原始碼之後修正的。原本我把它列成必要，
# 理由是「歷史的完整度基準是在有 ffmpeg 的條件下校準的」——**那是錯的**。
# 內建切檔按 MP3 frame 邊界切、無損、時長逐格累加，轉錄結果不會系統性改變。
# ffmpeg 真正做的是重新編碼成 16 kHz 單聲道 32 kbps，一段 20 分鐘從 ~19MB 降到
# ~5MB。它省的是上傳的牆鐘時間，不是正確性，而上傳不計入 RPD。
OPTIONAL_BY_LABEL = {
    "com.kenny.podfetch": {
        "ffmpeg": "省上傳量（一段 20 分鐘 ~19MB → ~5MB）。缺席時 podfetch 自動"
                  "改用內建切檔，無損但檔案大，吃 run_budget 的牆鐘時間。",
    },
}


def resolve(name: str, path: str = LAUNCHD_PATH):
    """在指定的 PATH 裡找一個可執行檔。**刻意不看 os.environ['PATH']。**"""
    for d in path.split(os.pathsep):
        p = Path(d) / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.kenny."


def declared_paths() -> dict:
    """從實際安裝的 plist 讀出它們宣告的 PATH。

    **不要用上面那個常數當答案。** 常數是「我以為排程看得到什麼」，plist 是
    「排程實際看得到什麼」——兩者不一致時，檢查會通過而排程會失敗。
    這跟 2026-08-19 的目的地守門是同一個形狀：驗證了物件，沒驗證身分。

    讀不到 plist 就回空 dict，呼叫端要把它當成「無法判定」而不是「沒問題」。
    """
    import plistlib
    out = {}
    if not AGENTS_DIR.is_dir():
        return out
    for f in sorted(AGENTS_DIR.glob(f"{LABEL_PREFIX}*.plist")):
        try:
            d = plistlib.loads(f.read_bytes())
        except Exception as e:
            out[f.stem] = {"error": f"{type(e).__name__}: {e}"}
            continue
        out[f.stem] = {"path": (d.get("EnvironmentVariables") or {}).get("PATH")}
    return out


def survey() -> dict:
    """每一支 plist 各自解析它自己需要的那幾個。"""
    plists = declared_paths()
    per = {}
    for label, info in plists.items():
        if info.get("error"):
            per[label] = {"error": info["error"]}
            continue
        path = info.get("path")
        per[label] = {
            "path": path,
            "declared": path is not None,
            "requires": REQUIRED_BY_LABEL.get(label),
            "found": {n: resolve(n, path)
                      for n in REQUIRED_BY_LABEL.get(label, [])}
            if path else None,
            "optional": {n: resolve(n, path)
                         for n in OPTIONAL_BY_LABEL.get(label, {})}
            if path else None,
        }
    return {"expected_path": LAUNCHD_PATH, "plists": per}
