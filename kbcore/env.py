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
# **每個 label 都要在這裡具名，即使它什麼都不需要**（`podfetch` 就是空陣列）。
# 沒登記時 `watch.external_binaries` 判 FAIL 而不是跳過 —— 那是刻意的：
# 「不知道它需要什麼」與「檢查過沒問題」是兩件事，而後者是預設會發生的謊。
#
# 2026-08-20 實測有效：`com.kenny.kbpublish.podcast` 一裝上去，看門狗那一輪
# 就叫了。新增排程而漏掉宣告，在這裡是紅的，不是安靜的。
REQUIRED_BY_LABEL = {
    "com.kenny.podfetch":          [],
    "com.kenny.kbpublish":         ["git"],
    "com.kenny.kbpublish.podcast": ["git"],
    "com.kenny.kbwatch":           ["git"],
    # bash 不列在這裡：它是 /bin/bash，跟 PATH 無關，缺席時 launchd 自己就起不來。
    # git 要列，因為 watch_sentinel 會 fetch，而 healthcheck 明訂不碰 git。
    "com.kenny.kbwatch.podcast":   ["git"],
    "com.kenny.kbpublish.chart":   ["git"],
    "com.kenny.kbwatch.chart":     ["git"],
    "com.kenny.kbwatch.research":  ["git"],
    "com.kenny.kbpublish.research": ["git"],
    # 2026-08-31：**第四次同一形狀。** 每天 06:00 把抽過的 PDF 從 inbox 移到
    # `~/broker-research/filed/<YYYY-MM>/`，跑的是 venv python ＋
    # `scripts/research/file_reports.py`。整支沒有 `subprocess`、沒有
    # `shutil.which`、沒有 `os.system` —— **空陣列不是「還沒想」，是「想過了，
    # 答案是零」**（同 `kbprefetch.chart`）。
    # 它從裝上去到 08-31 都沒被登記，於是 `watch.external_binaries` 一直 FAIL，
    # 而 FAIL 的看門狗不更新 heartbeat。
    "com.kenny.kbfile.research":   [],
    # 2026-08-24：**第三次同一形狀。** 這一支已經裝在機器上（`~/Library/LaunchAgents/`
    # 有 `com.kenny.kbpublish.convergence.plist`），但沒登記進來 ——
    # `watch.external_binaries` 對「不在 REQUIRED_BY_LABEL 裡」是 FAIL，
    # 而 FAIL 的看門狗不更新 heartbeat，於是**整個哨兵會被一支沒登記的 plist 靜音**。
    # 08-21 那次是四支裡三支沒登記、08-23 那次是 kbpublish.bubble，這次是 convergence。
    # 它跑的是 venv python ＋ `tools/publish.py`（outbox `~/outbox/convergence`、
    # repo `~/convergence-weekly`、系統 id `convergence-weekly`），與其他 kbpublish.*
    # 同一條路徑，所以需要的外部指令一樣是 git。
    #
    # **裝一支新 plist 有兩個動作，不是一個**：載進 launchctl、登記進這張表。
    # 只做第一個，系統會跑得好好的，而看門狗會安靜地紅到有人來看。
    "com.kenny.kbpublish.convergence": ["git"],
    # 2026-08-21：下面四支裡有三支是 08-20／08-21 裝上去的，而**沒有一支被登記進來**。
    # 這個機制是對的（沒登記就 FAIL），漏的是有人去登記 —— 兩件事。
    "com.kenny.kbcorepush":        ["git"],   # push_kbcore.py 自動 commit kb-core
    # 這兩支只跑 venv 裡的 python（絕對路徑），不叫任何外部指令。
    # **空陣列不是「還沒想」，是「想過了，答案是零」** —— 沒登記才是紅的。
    "com.kenny.kbprefetch.chart":  [],
    "com.kenny.kbdocx.podcast":    [],
    # 2026-08-24 新增。`kbusage.sh` 呼叫的外部東西只有兩個 python，兩個都是
    # **絕對路徑**（`~/.venvs/kb/bin/python` 跑報表、`/usr/bin/python3` 解 sidecar），
    # 其餘是 date／wc／tail／mv／rm／grep／stat／mkdir —— 與 /bin/bash 同一類，
    # 是 macOS 基礎系統的一部分，缺了的話這台機器已經不能開機了，
    # **不是 PATH 會不會解析得到的問題**。所以答案是零，不是還沒想。
    "com.kenny.kbusage":           [],
    # 2026-08-24 新增。缺列哨兵 `tools/usage_gaps.py`：plist 直接跑 venv 的
    # python（絕對路徑），程式裡**沒有任何 subprocess** —— 它只讀七個回執、
    # 一個 CSV，寫一份 markdown。**空陣列是想過的答案，不是還沒想。**
    "com.kenny.kbgaps":            [],
    # 2026-08-24 新增。掃描式量測 `tools/usage_scan.py` **會跑 git**：
    # 上界取自資料 repo 裡 `data/<日期>.json` 的首次 commit
    # （`git log --diff-filter=A`）—— 唯讀、不碰索引、不留 index.lock，
    # 所以不會擋住每 60 秒一次的 kbpublish.*。
    # 它另外會 spawn venv 的 python 跑 usage_report.py，那是絕對路徑。
    "com.kenny.kbscan":            ["git"],
    # 2026-08-23：這一支讓看門狗連續 FAIL，而 FAIL 的看門狗不更新 heartbeat ——
    # `advisory-rewrite/sentinel/heartbeat.json` 因此停在 08-22 07:20Z、`latest_date`
    # 停在 08-22，即使 08-23 已經正常發布。**一個永遠紅的看門狗把真訊號埋掉了。**
    #
    # 它是唯一一支不跑 `tools/publish.py` 的：plist 直接跑 venv 的 python 執行
    # `~/Projects/ai-bubble-monitor/scripts/auto_publish.py`，沒有包裝腳本，
    # plist 正本也在那個 repo。
    #
    # **同日在機器上實測過，不是推定**（工作階段掛載不到那個 repo，所以是在終端機跑的）：
    # 掃 `auto_publish.py` 與 `gate.py` 的所有 list 字面值首元素，只有 `git` 與 `composite`
    # 兩個，而 `composite` 是 `gate.py:76` 的必要 JSON 鍵清單、不是指令。
    # git 共 12 個呼叫點（auto_publish 10、gate 2），全走同一個 `subprocess.run` 包裝，
    # **整個 repo 沒有任何 `shell=True`** —— 所以 PATH 白名單的推理成立，
    # 沒有第二條經由 shell 展開的路徑。
    # 該 plist 宣告的 PATH 是 `/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`，
    # **沒有 `/opt/homebrew/bin`**；用 `env -i` 只留那個 PATH 實測，git 解析到
    # `/usr/bin/git`（Xcode CLT 那支）。**它不依賴 Homebrew，這是它的運氣不是它的設計** ——
    # 哪天有人往那支程式加一個只有 Homebrew 才有的指令，這條會叫，而那正是它該做的事。
    "com.kenny.kbpublish.bubble":  ["git"],
    # 2026-08-23：advisory 的保底層預抓。用 curl 抓 origin 上的 raw JSON 到
    # `~/outbox/floor/`（2026-08-28 由 `~/.advisoryfetch/` 搬過來），
    # **不跑任何 git**（跑 git 會與每 60 秒的 kbpublish 搶 index.lock）。
    #
    # 2026-08-28 新增的本機自取備援叫的是 `~/.venvs/kb/bin/python` 與
    # `/usr/bin/python3`，**兩個都是絕對路徑、與 PATH 無關**，所以這一列不變 ——
    # 同 kbprefetch.chart 與 kbusage 的判斷。列進來的唯一標準是「會不會因為
    # launchd 的 PATH 只有四個目錄而找不到」。
    "com.kenny.kbprefetch.advisory": ["curl"],
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
