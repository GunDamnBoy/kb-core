#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
podfetch — 每天自動抓新集數的音檔，用 Gemini API 轉成帶講者標籤的逐字稿。

零外部相依：只用 Python 標準函式庫。MP3 直接在 frame 邊界切段，不重新編碼。

=== 2026-08-02 全日除錯後定案的設計（每一條都有實測依據）===

額度
  1. 免費層的瓶頸是 RPD，不是 TPM（250K 實測只用到 12%）。
     新版 Flash 每天只有 10-20 個請求（會浮動）；**Flash-Lite 3.1／3.5 有 500 個**。
     → 2026-08-05 起改為 **Lite 優先、Flash 備援**（config 的 prefer_lite），
       因為把最稀缺的資源排前面等於每天開場就燒光它。
     → 日額度用盡或 404 進 EXHAUSTED（本次永久除名）；500/503 只進 OVERLOADED
       冷卻一段時間後自動回池——**暫時性錯誤不可以產生永久性後果**（2026-08-06）。
  2. 20 分鐘一段、走 Files API 上傳（上傳免費且不計入 RPD）。
     曾經為了省 RPD 改成 30 分鐘，結果撞上輸出上限，得不償失。

輸出（這一段是最容易重蹈覆轍的地方）
  3. **一定要明確指定 maxOutputTokens。** 預設約 8192，而 Gemini 3.x 的 thinking
     token 也算在輸出預算內——實測導致多段被腰斬（一致卡在 5,600-6,200 字，
     那個一致性就是天花板的指紋），最慘一段 thinking 吃光預算只吐出 6 個字。
  4. 各模型接受的 generationConfig 不同（Flash 吃 thinkingBudget，Lite 不吃），
     而 400 的錯誤訊息是通用的，看不出是哪個欄位。
     → 探測階段就用小額度把可用組合試出來，記在 MODEL_GENCFG。

品質檢查（Gemini 會安靜地出錯，這是唯一的防線）
  5. 計字數前必須先剝掉「[MM:SS] 講者姓名：」前綴。不剝的話，交替頻繁的節目
     會因為標籤多而被高估近五成，完整度就變成在量格式而不是量內容。
  6. 四道檢查缺一不可：
       絕對值 — 低於該節目語速基準的 55%（MIN_RATIO，抓整集壓縮）
       相對值 — 低於本集各段中位數的 60%（REL_RATIO，抓單段掉字）
       上界   — 高於本集各段中位數的 160%（HIGH_RATIO，抓段級異常）
       跳針   — collapse_loops() 把連續重複 20 次以上的 token 排除在字數之外
     基準值一律引用 WORDS_PER_MIN／shows.json 的 wpm，不要在說明或訊息裡寫死
     數字——它已經改過三代（130→165→200），寫死的每一處都會變成過期的假事實。
     語速因節目而異極大（17 檔實測 122-218 字/分），只靠絕對值一定會失準。
     另外注意「絕對值」只抓**過低**，完整度超標不會產生任何 warning，
     因此 wpm 的高低不影響 status 是否為 DEGRADED（2026-08-09 訂正）。
     注意跳針一旦被 collapse_loops 扣掉，段級的「上界」就看不到單 token 跳針了，
     位置資訊改由 loop_segs 記錄（2026-08-08）。
  7. 時間軸的可疑訊號走獨立的 timestamp_notes，同樣不進 warnings。兩種訊號：
     最大時間戳溢出片長 >25%（08-11 的 20VC 溢出 1888%、08-14 的 TIP837 224%，
     兩集完整度都正常、status 都是 OK，三天無人看見）；以及「無戳時間佔比 >30%
     **且** 完整度 <0.85」。第二條刻意要求兩個訊號同時成立——長篇獨白與真跳段
     長得一樣，只看間隙會對 72 集報 15 集，那就是講者檢查初版的同一種雜訊。
  9. 講者標記的可疑訊號走獨立的 speaker_notes，**不進 warnings、不影響 status**——
     兩者是不同維度，混在一起會讓完整度正常的集數被誤標為 DEGRADED（2026-08-07）。

其他
  7. 處理順序照日報優先序（All-In 最前），額度不足時犧牲邊際節目而非主秀。
  8. 視窗以 last_run_utc 為準；有集數未完成就不推進時間戳，下次自動接續。
     已完成的段落留在 cache/，重跑不會重花配額。
"""

import base64
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

# kb-core 的根，為了 import kbcore.transcript。**區塊重播的偵測只有一份實作**，
# 而它同時被這裡（決定 status）與 podcast_verify（檢查）用 ——
# 各寫一次的話，寬鬆的那一份就是下游會讀到的那一份（2026-08-21 實測）。
# scripts/podcast/podfetch.py → 往上三層才是 kb-core。**兩層只到 scripts/。**
_KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _KB)
from kbcore.transcript import significant_repeats                    # noqa: E402

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".podfetch")
# 門檻的家在 anchors，這裡只當讀者。讀不到就大聲失敗——
# **門檻取不到是設定壞了，不是資料壞了**，安靜跳過會讓這條偵測變成永遠不觸發。
_ANCHORS = json.load(open(os.path.join(_KB, "podcast", "anchors.json"),
                          encoding="utf-8"))["quality"]
CONFIG_PATH = os.path.join(BASE, "config.json")
KEY_PATH = os.path.join(BASE, "gemini.key")
STATE_PATH = os.path.join(BASE, "state.json")
SHOWS_PATH = os.path.join(BASE, "shows.json")
LOG_DIR = os.path.join(BASE, "logs")
CACHE_DIR = os.path.join(BASE, "cache")

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD_ROOT = "https://generativelanguage.googleapis.com/upload/v1beta/files"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

WORDS_PER_MIN = 200        # 全域預設。可在 shows.json 用 "wpm" 逐檔覆寫。
# 沿革：130（初版）→ 165（2026-08-06）→ 200（2026-08-09，17 檔實測中位數，
# 範圍 122-218，已排除跳針污染的樣本）。對談型（Bloomberg、All-In、MiB、20VC）
# 約 210-220；訪談型（In Good Company、MacroVoices）約 160；ILTB 實測 122。
# 差異大的用 shows.json 的 "wpm" 覆寫，目前 7 檔有設。
#
# **這個常數影響什麼、不影響什麼——不要搞混（2026-08-09 訂正）：**
#   影響：① 完整度分母 `expected_total`（:1116），也就是使用者看到的 1.0x 那個數字；
#         ② 段級重試門檻 `expected`（:1021），**上修 wpm 會讓門檻變嚴、更容易重試**；
#         ③ 沒有可用段落時 `median_rate` 的後備值（:1099）。
#   不影響：**status 是否為 DEGRADED 與「超標」無關。** status 只看 `warnings`，
#         而 warnings 只有三個來源：ratio < MIN_RATIO（缺字）、段級語速偏離
#         *本集中位數*（REL_RATIO／HIGH_RATIO，完全不看 wpm）、跳針剔除。
#         完整度 1.4 不會產生任何 warning。校準 wpm 是為了讓顯示的完整度
#         「正常≈1.0」而有可讀性，**不是為了減少 DEGRADED**。
MIN_RATIO = 0.55             # 低於基準這個比例視為內容缺漏
REL_RATIO = 0.60             # 低於本集中位數這個比例視為該段缺漏
HIGH_RATIO = 1.60            # 高於中位數這個比例視為跳針重複（LLM 在長音檔上的典型失敗）

# 逐字稿每行開頭是「[MM:SS] 講者姓名：」，計字數時必須先剝掉，
# 否則交替頻繁的節目（Bloomberg、20VC）會因為標籤多而被高估，
# 完整度就變成在量格式而不是量內容。
_TURN_PREFIX = re.compile(
    r"^\s*\[\d{1,3}:\d{2}(?::\d{2})?\]\s*(?:[^:\n]{0,60}?:\s*)?", re.MULTILINE)


_TS = re.compile(r"^(\s*)\[(\d{1,3}):(\d{2})(?::(\d{2}))?\]", re.MULTILINE)


ABS_TS_TOLERANCE = 180       # 判定「模型已輸出絕對時間」時，第一個時間戳容許離段起點多遠


def hhmmss(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)


def offset_timestamps(text, offset_seconds):
    """每段的時間戳都從 00:00 重新起算，合併前要位移成整集的絕對時間，
    否則同一個 [18:49] 會在多段裡重複出現，日報引用時根本無法定位。

    **但 Gemini 有時會直接輸出絕對時間**（prompt 告訴它本段涵蓋整集的哪一段，
    它就照那個範圍寫），這時再加一次 offset 就會變成雙重偏移。2026-08-08 實測：
    第 2 段標成 40:00–59:52、實際是 20:00–39:52，而同一集的第 3 段卻是對的——
    **同一次執行裡時而遵守時而不遵守，所以不能只靠 prompt**。

    判斷方式：第一個時間戳若**貼近**本段的絕對起點（±ABS_TS_TOLERANCE 秒），
    就當成模型已經寫了絕對時間。不要用「離 off 比離 0 近」——那個判定線落在
    off/2，第 2 段只有 10:00，段首十分鐘廣告就會誤判。
    """
    off = int(offset_seconds)
    if off > 0:
        m0 = _TS.search(text or "")
        if m0:
            a, b, c = int(m0.group(2)), int(m0.group(3)), m0.group(4)
            first = (a * 3600 + b * 60 + int(c)) if c else (a * 60 + b)
            # 判定「已是絕對時間」要求**貼近** off，不能只是「離 off 比離 0 近」。
            # 後者的判定線落在 off/2：第 2 段 off=1200 時門檻只有 10:00，只要該段
            # 開頭有十分鐘廣告或音樂讓第一個時間戳落在 10:00 之後，整段就會被誤判
            # 成絕對時間而跳過位移，合併後時間軸倒退 20 分鐘。
            if abs(first - off) <= ABS_TS_TOLERANCE:
                log("    第一個時間戳 %s 貼近本段絕對起點，判定模型已輸出絕對時間，"
                    "跳過 +%d 秒位移" % (hhmmss(first), off))
                # 仍要走一次 fix()（off 歸零）把格式正規化成 [MM:SS]／[H:MM:SS]，
                # 否則模型若寫了 [105:30] 這種三位數分鐘，下游的 SPEAKER_LINE
                # 匹配不到，會誤報成「裸時間戳」。
                off = 0

    def fix(m):
        indent, a, b, c = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        secs = (a * 3600 + b * 60 + int(c)) if c else (a * 60 + b)
        secs += off
        h, rem = divmod(secs, 3600)
        mi, se = divmod(rem, 60)
        return "%s[%d:%02d:%02d]" % (indent, h, mi, se) if h else "%s[%02d:%02d]" % (indent, mi, se)

    return _TS.sub(fix, text or "")


_LOOP = re.compile(r"(?<!\S)(\S+)(?:\s+\1){19,}(?!\S)", re.I)


def collapse_loops(text):
    """把「同一個 token 連續重複 20 次以上」壓成一次，回傳 (壓縮後文字, 剔除字數)。

    2026-08-08 教訓：Gemini 在長音檔上會整行跳針——The Compound 有一行是 28,122
    個重複的「I」、Hard Fork 有 9,521 個「let's」。這些字如果計入總數，**完整度
    指標會完全反向**：內容嚴重缺漏的集數顯示成「超標 336%」。實測壓掉之後
    3.36 → 1.10、1.93 → 1.10，與人工評估吻合。
    """
    if not text:
        return "", 0
    before = len(text.split())
    out = _LOOP.sub(lambda m: m.group(1), text)
    return out, before - len(out.split())


def spoken_words(text):
    """只數真正被講出來的字，不含時間戳、講者標籤，也不含跳針的重複。"""
    body = _TURN_PREFIX.sub("", text or "")
    return len(collapse_loops(body)[0].split())

# Gemini 3.x 預設會做 thinking，而 thinking token 也吃輸出預算；
# 若不指定 maxOutputTokens，預設約 8192，30 分鐘的逐字稿必定被腰斬。
# 2026-08-02 實測：多段卡在 5,600-6,200 字（天花板的指紋），
# 最慘的一段 thinking 吃光預算只吐出 6 個字。
MAX_OUTPUT_TOKENS = 32768

# 不同模型接受的 generationConfig 不一樣：2026-08-02 實測 gemini-3.5-flash 接受
# 「maxOutputTokens 32768 ＋ thinkingBudget 0」，但 Flash-Lite 直接回 400
# INVALID_ARGUMENT，而且訊息是通用的「Request contains an invalid argument.」，
# 看不出是哪個欄位。所以改成由多到少逐一試，探測階段就決定好，之後整段沿用。
MODEL_GENCFG = {}
EXHAUSTED = set()            # 本次執行中已確定日額度用完（或 404）的模型——永久除名
OVERLOADED = {}              # 模型 → 冷卻到期的 time.time()。500／503 專用，會自動回池
NOT_FOUND = set()            # 本次執行中 404 的模型——探測快取已過期的訊號，隔天強制重測


def gen_variants(max_tokens):
    return [
        {"temperature": 0, "maxOutputTokens": max_tokens,
         "thinkingConfig": {"thinkingBudget": 0}},
        {"temperature": 0, "maxOutputTokens": max_tokens},
        {"temperature": 0, "maxOutputTokens": 16384,
         "thinkingConfig": {"thinkingBudget": 0}},
        {"temperature": 0, "maxOutputTokens": 16384},
        {"temperature": 0, "maxOutputTokens": 8192},
        {"temperature": 0},
    ]


def describe_cfg(cfg):
    bits = []
    if "maxOutputTokens" in cfg:
        bits.append("out=%d" % cfg["maxOutputTokens"])
    else:
        bits.append("out=預設")
    bits.append("thinking=off" if "thinkingConfig" in cfg else "thinking=預設")
    return "、".join(bits)


def log(msg):
    line = "[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, dt.date.today().isoformat() + ".log"),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def http_get(url, headers=None, timeout=120):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_post_json(url, payload, headers, timeout=1200):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": UA}
    h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- 例外

class QuotaExhausted(Exception):
    """所有模型的日額度都用完了。"""


class DailyQuotaForModel(Exception):
    """單一模型的 RPD 用完，可以換下一個模型。"""


class ModelUnavailable(Exception):
    """模型對本專案不開放（404）。"""


class ModelOverloaded(Exception):
    """模型暫時過載（500／503）。

    2026-08-04 教訓：503 是「這個模型現在忙」，不是額度問題，但舊版會在
    同一個模型上把 5 次重試燒完再判定整集失敗——當天 Flash 兩個模型的 RPD
    都爆掉（21/20），而還有 491 次額度的 Flash-Lite 完全沒被用到，三集因此
    白白失敗。重試同樣計入 RPD，所以死守單一模型是雙重浪費。
    現在改為短 retry 兩次就丟出本例外，由呼叫端把該模型放進 `OVERLOADED`
    冷卻一段時間（`overload_cooldown_seconds`），到期自動回池。

    **不要再併回 404／日額度那個 handler。** 2026-08-06 就是因為兩者共用
    `EXHAUSTED`，一次過載尖峰在 77 秒內把三個 500 RPD 的 Lite 全部永久除名，
    剩 10 RPD 的 Flash 扛完整場。暫時性錯誤不可以產生永久性後果。
    """


# ---------------------------------------------------------------- 速率控制

class RateLimiter(object):
    def __init__(self, min_interval):
        self.min_interval = float(min_interval)
        self._next_ok = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            if now < self._next_ok:
                time.sleep(self._next_ok - now)
                now = time.time()
            self._next_ok = now + self.min_interval


LIMITER = RateLimiter(10.0)


def parse_quota_error(raw):
    """從 429 內容取出（建議等待秒數, 配額名稱, 是否為每日配額）。"""
    delay, metric, per_day = None, "", False
    try:
        err = json.loads(raw).get("error", {})
        for d in err.get("details", []):
            rd = d.get("retryDelay")
            if rd:
                m = re.match(r"([0-9.]+)s", str(rd))
                if m:
                    delay = int(float(m.group(1))) + 2
            for v in d.get("violations", []) or []:
                metric = v.get("quotaId") or v.get("quotaMetric") or metric
        if not metric:
            metric = err.get("message", "")[:120]
    except Exception:
        metric = (raw or "")[:120]
    blob = (metric or "") + (raw or "")
    per_day = ("PerDay" in blob) or ("per day" in blob.lower())
    if delay is None:
        m = re.search(r"retryDelay[\"':\s]+([0-9.]+)s", raw or "")
        if m:
            delay = int(float(m.group(1))) + 2
    return delay, metric, per_day


# ---------------------------------------------------------------- 偵測新集數

def itunes_lookup(apple_id, limit):
    # cb 是必要的，不是保險：iTunes 會把回應綁在「確切的查詢字串」上快取，
    # 過期時同一個網址可以連續數天回同一份舊資料（2026-08-15 實測 US 商店
    # 停在 07-31、落後 15 天），而 HTTP 仍是 200、discover() 看不到任何錯誤，
    # 症狀與「今天真的沒有新集數」完全相同。加上變動參數即繞開該快取項。
    # 註：路徑前綴形式（itunes.apple.com/gb/lookup）在本環境回空白內容，
    # 不能當替代方案；要換商店請用 &country=GB。
    url = ("https://itunes.apple.com/lookup?id=%s&media=podcast"
           "&entity=podcastEpisode&limit=%d&cb=%d"
           % (apple_id, limit, int(time.time())))
    return json.loads(http_get(url).decode("utf-8", "replace")).get("results", [])


def discover(shows, since_utc, seen_ids, priority):
    """回傳 (符合視窗的集數清單, 全庫最新一集的 UTC 時間)。

    第二個回傳值是 2026-08-15 假零集事故加的**健全性對照基準**。它用的是**已經
    抓回來的資料**，不發任何額外請求——把 23 檔所有集數（不分視窗、不分是否看過）
    裡最新的那一筆時間拿出來。正常日它會是「幾小時前」（23 檔裡有每個交易日都發
    的 Bloomberg）；事故日它是 **15 天前**，因為 iTunes 回的整份快取都是舊的。
    **「所有節目同時安靜三天以上」在現實中不會發生，只會是查詢壞了。**
    """
    found = []
    newest = None
    for key, s in shows.items():
        try:
            results = itunes_lookup(s["appleId"], int(s.get("limit", 8)))
        except Exception as e:
            log("  ! %s 查詢失敗：%s" % (key, e))
            continue
        for x in results:
            if x.get("wrapperType") != "podcastEpisode":
                continue
            rd = x.get("releaseDate")
            if not rd:
                continue
            try:
                t = dt.datetime.strptime(rd, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            # 先更新對照基準再篩視窗——**這個數字必須看到所有集數**，
            # 只看視窗內的就永遠不會告訴你「視窗內為什麼是空的」。
            if newest is None or t > newest:
                newest = t
            if t < since_utc:
                continue
            tid = str(x.get("trackId"))
            if tid in seen_ids:
                continue
            if not x.get("episodeUrl"):
                log("  ! %s「%s」沒有音檔網址，略過" % (key, (x.get("trackName") or "")[:50]))
                continue
            found.append({
                "showKey": key,
                "show": s["name"],
                "hosts": s.get("hosts", ""),
                "wpm": s.get("wpm"),
                "trackId": tid,
                "title": x.get("trackName") or "",
                "releaseDate": rd,
                "durationMs": int(x.get("trackTimeMillis") or 0),
                "audioUrl": x["episodeUrl"],
                "description": re.sub(r"<[^>]+>", " ", x.get("description") or "")[:1500],
                "appleUrl": "https://podcasts.apple.com/us/podcast/id%s?i=%s"
                            % (s["appleId"], tid),
            })
    # 依日報優先序排，額度不夠時先犧牲邊際節目而不是主秀
    def rank(e):
        try:
            return (priority.index(e["showKey"]), e["releaseDate"])
        except ValueError:
            return (len(priority), e["releaseDate"])
    found.sort(key=rank)
    return found, newest


# ---------------------------------------------------------------- MP3 處理

_BR_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_BR_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _id3_skip(data):
    if data[:3] == b"ID3" and len(data) > 10:
        size = (((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) |
                ((data[8] & 0x7F) << 7) | (data[9] & 0x7F))
        off = 10 + size + (10 if data[5] & 0x10 else 0)
        if 0 < off < len(data):
            return off
    return 0


def iter_mp3_frames(data):
    i = _id3_skip(data)
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        b1, b2 = data[i + 1], data[i + 2]
        ver = (b1 >> 3) & 0x03
        layer = (b1 >> 1) & 0x03
        if ver == 1 or layer != 1:
            i += 1
            continue
        br_i = (b2 >> 4) & 0x0F
        sr_i = (b2 >> 2) & 0x03
        pad = (b2 >> 1) & 0x01
        if br_i in (0, 15) or sr_i == 3:
            i += 1
            continue
        sr = _SR[ver][sr_i]
        if ver == 3:
            br, spf = _BR_V1_L3[br_i], 1152
            flen = (144 * br * 1000) // sr + pad
        else:
            br, spf = _BR_V2_L3[br_i], 576
            flen = (72 * br * 1000) // sr + pad
        if br == 0 or flen <= 4 or i + flen > n:
            i += 1
            continue
        yield i, flen, spf / float(sr)
        i += flen


def mp3_duration(path):
    with open(path, "rb") as f:
        return sum(d for _, _, d in iter_mp3_frames(f.read()))


def split_mp3_pure(src, outdir, seconds, max_bytes):
    with open(src, "rb") as f:
        data = f.read()
    chunks = []
    start = None
    cbytes = cdur = 0.0
    end = None
    idx = 0
    first = True
    for off, flen, dur in iter_mp3_frames(data):
        if first:
            first = False
            head = data[off:off + min(flen, 256)]
            if b"Xing" in head or b"Info" in head or b"VBRI" in head:
                continue          # 這個 frame 記的是整檔長度，會讓解碼器誤判
        if start is None:
            start, cbytes, cdur = off, 0, 0.0
        cbytes += flen
        cdur += dur
        end = off + flen
        if cdur >= seconds or cbytes >= max_bytes:
            p = os.path.join(outdir, "part_%03d.mp3" % idx)
            with open(p, "wb") as g:
                g.write(data[start:end])
            chunks.append((p, cdur))
            idx += 1
            start = None
    if start is not None and end and end > start:
        p = os.path.join(outdir, "part_%03d.mp3" % idx)
        with open(p, "wb") as g:
            g.write(data[start:end])
        chunks.append((p, cdur))
    return chunks


def split_with_ffmpeg(src, outdir, seconds):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
           "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
           "-f", "segment", "-segment_time", str(seconds),
           os.path.join(outdir, "part_%03d.mp3")]
    subprocess.run(cmd, check=True)
    paths = sorted(os.path.join(outdir, n) for n in os.listdir(outdir)
                   if n.startswith("part_") and n.endswith(".mp3"))
    return [(p, mp3_duration(p)) for p in paths]


def split_audio(src, outdir, seconds, max_bytes):
    if shutil.which("ffmpeg"):
        try:
            out = split_with_ffmpeg(src, outdir, seconds)
            if out:
                return out, "ffmpeg"
        except Exception as e:
            log("  ! ffmpeg 切段失敗（%s），改用內建切檔" % e)
            for n in os.listdir(outdir):
                try:
                    os.remove(os.path.join(outdir, n))
                except OSError:
                    pass
    out = split_mp3_pure(src, outdir, seconds, max_bytes)
    if not out:
        raise RuntimeError("無法解析此 MP3 的框架結構，切段失敗")
    return out, "pure-python"


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=900) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, 1024 * 256)
    return os.path.getsize(dest)


# ---------------------------------------------------------------- Files API

def upload_file(api_key, path, mime="audio/mpeg"):
    """上傳到 Gemini Files API。上傳免費且不計入 RPD，只有 generateContent 才算一次請求。"""
    size = os.path.getsize(path)
    start = urllib.request.Request(
        UPLOAD_ROOT,
        data=json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
        headers={"x-goog-api-key": api_key,
                 "X-Goog-Upload-Protocol": "resumable",
                 "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(size),
                 "X-Goog-Upload-Header-Content-Type": mime,
                 "Content-Type": "application/json",
                 "User-Agent": UA},
        method="POST")
    with urllib.request.urlopen(start, timeout=180) as r:
        upload_url = (r.headers.get("X-Goog-Upload-URL")
                      or r.headers.get("x-goog-upload-url"))
    if not upload_url:
        raise RuntimeError("Files API 未回傳上傳網址")
    with open(path, "rb") as f:
        blob = f.read()
    put = urllib.request.Request(
        upload_url, data=blob,
        headers={"Content-Length": str(size),
                 "X-Goog-Upload-Offset": "0",
                 "X-Goog-Upload-Command": "upload, finalize",
                 "User-Agent": UA},
        method="POST")
    with urllib.request.urlopen(put, timeout=1800) as r:
        info = json.loads(r.read().decode("utf-8"))
    fi = info.get("file") or {}
    uri, name, state = fi.get("uri"), fi.get("name"), fi.get("state")
    if not uri:
        raise RuntimeError("Files API 回應缺少 uri：%s" % json.dumps(info)[:200])
    for _ in range(80):
        if state == "ACTIVE":
            return uri, name
        if state == "FAILED":
            raise RuntimeError("Files API 處理失敗")
        time.sleep(3)
        try:
            raw = http_get("%s/%s" % (API_ROOT, name),
                           headers={"x-goog-api-key": api_key, "User-Agent": UA})
            state = json.loads(raw.decode("utf-8")).get("state")
        except Exception:
            pass
    raise RuntimeError("上傳的檔案遲遲未就緒（state=%s）" % state)


def delete_file(api_key, name):
    if not name:
        return
    try:
        req = urllib.request.Request("%s/%s" % (API_ROOT, name),
                                     headers={"x-goog-api-key": api_key,
                                              "User-Agent": UA},
                                     method="DELETE")
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:
        pass


# ---------------------------------------------------------------- 模型挑選

_BAD_MODEL_TOKENS = ("embedding", "image", "imagen", "veo", "tts", "aqa",
                     "gemma", "learnlm", "vision", "-tuning", "live",
                     "native-audio", "dialog", "robotics", "computer-use")

_PROBE_MP3_B64 = (
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//NYwAAAAAAAAAAAAEluZ"
    "m8AAAAPAAAAEwAAA2AAQEBAQEBKSkpKSlVVVVVVYGBgYGBgampqamp1dXV1dYCAgICAioqKioqKlZWVlZ"
    "WgoKCgoKqqqqqqtbW1tbW1wMDAwMDKysrKytXV1dXV4ODg4ODg6urq6ur19fX19f//////AAAAAExhdmM"
    "1OC4xMwAAAAAAAAAAAAAAACQDAAAAAAAAAANg6odHXAAAAAAAAAAAAAAA//MYxAAAAANIAAAAAExBTUUz"
    "LjEwMFVVVVVVVVVVVVVVVUxB//MYxBcAAANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVVUxB//MYxC4AA"
    "ANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVVUxB//MYxEUAAANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVV"
    "VVVUxB//MYxFwAAANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVVUxB//MYxHMAAANIAAAAAE1FMy4xMDB"
    "VVVVVVVVVVVVVVVVVVUxB//MYxIoAAANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVVUxB//MYxKEAAANI"
    "AAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVVUxB//MYxLgAAANIAAAAAE1FMy4xMDBVVVVVVVVVVVVVVVVVV"
    "VVV//MYxM8AAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//MYxOYAAANIAAAAAFVVVVVVVVVVVV"
    "VVVVVVVVVVVVVVVVVV//MYxOgAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
)


def list_models(api_key):
    raw = http_get(API_ROOT + "/models",
                   headers={"x-goog-api-key": api_key, "User-Agent": UA})
    return [m["name"].split("/")[-1]
            for m in json.loads(raw.decode("utf-8")).get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or [])]


# 合併後的時間戳超過一小時會變成 [H:MM:SS]，正則一定要兩種都吃——只認 [MM:SS]
# 的話，一小時以上的節目後半整段不會進統計（實測 MiB 234 行只有 47 行被檢查）。
SPEAKER_LINE = re.compile(r"^\[(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\]\s*([^:：]{1,48})[:：]")


_ANY_TS = re.compile(r"^\s*\[(?:(\d+):)?(\d{1,2}):(\d{2})\]", re.M)
TS_OVERFLOW = 0.25      # 最大時間戳超出片長這個比例就出聲
TS_DARK_GAP = 90        # 相鄰時間戳間隔超過這麼多秒，超出的部分算「無戳時間」


TS_DARK_SHARE = 0.30    # 無戳時間佔片長超過這個比例
TS_DARK_RATIO = 0.85    # …**且**完整度低於這個值，才算可疑（兩個訊號要同時成立）


def check_timestamps(full, duration_s, ratio):
    """時間軸的機械檢查——完整度與講者檢查都抓不到這一類（2026-08-14 新增）。

    **為什麼需要它**：08-11 的 20VC 最大時間戳跑到 1,192 分鐘（片長 59 分，
    溢出 1888%）、08-14 的 TIP837 跑到 253 分（片長 78 分，溢出 224%）。
    兩集的 completeness 都正常（0.91／0.98）、status 都是 OK，**三天來沒有任何
    機制看見它**——講者檢查只抓到副作用（「整段錯置」訊號），時間軸崩壞本身隱形。

    **它為什麼要緊**：時間戳決定摘譯的章節切分。08-14 那集是子代理自己發現異常、
    改用主題轉換分節的——又一次「執行者靠自覺補上規格缺口」。

    **刻意不併進 `warnings`。** `warnings` 直接決定 status，而 DEGRADED 的定義是
    「內容不足」；時間軸壞掉不代表內容缺漏（那兩集完整度都正常），併進去會用一個
    錯的理由把好集數標成降級。這是 2026-08-07 講者檢查踩過的坑，不要再踩一次。

    回傳一組人讀的字串，空清單代表沒有可疑訊號。
    """
    secs = sorted({int(h or 0) * 3600 + int(m) * 60 + int(s)
                   for h, m, s in _ANY_TS.findall(full)})
    if len(secs) < 5 or duration_s <= 0:
        return []
    out = []
    over = (secs[-1] - duration_s) / duration_s
    if over > TS_OVERFLOW:
        out.append("時間戳最大值 %d 分，片長只有 %d 分（溢出 %.0f%%）——"
                   "**時間軸不可信，摘譯時不要依時間戳切章節，改用主題轉換判定**"
                   % (secs[-1] // 60, duration_s // 60, over * 100))
    # 大間隙**單獨看是雜訊**——長篇獨白（時間戳只在換人時出現）與真的跳段長得一樣。
    # 全庫實測：只看間隙會對 72 集報 15 集，其中多數完整度正常（Odd Lots 1.03、
    # Pivot 1.12），那就是 2026-08-07 講者檢查初版「九集報八集」的同一種失敗。
    # 所以改成**兩個獨立訊號同時成立才出聲**：無戳時間佔比高、且完整度也偏低。
    # （「與完整度一起看」這件事應該由程式做，不是寫進訊息叫人自己判斷。）
    dark = sum(g - TS_DARK_GAP for g in
               (b - a for a, b in zip(secs, secs[1:])) if g > TS_DARK_GAP)
    if dark > TS_DARK_SHARE * duration_s and ratio < TS_DARK_RATIO:
        out.append("有 %d 分鐘（佔片長 %.0f%%）落在相鄰時間戳的大間隙裡，"
                   "而完整度只有 %.2f——**兩個訊號同時指向跳段**，"
                   "摘譯時要在正文與 source 標明哪幾段是缺的"
                   % (dark // 60, dark / duration_s * 100, ratio))
    return out


def check_speaker_labels(full, hosts):
    """講者標記的合理性檢查——完整度檢查完全抓不到這一類（2026-08-07）。

    當天九集全部 status=OK，卻有五集的講者標記需要人工校正：整段標錯人、
    廣告與台呼被歸給主持人、同一集裡標記中途翻轉、多位來賓被合併成一個。
    **錯的名字會變成對真實人物的錯誤指涉，而且比缺名字難發現得多。**

    這裡只做機械式的可疑訊號偵測，不試圖判斷誰是誰——判斷交給讀逐字稿的人，
    這支腳本的工作是讓問題「可見」。
    """
    out = []
    known = {h.strip().lower() for h in re.split(r"[,，、/]| and ", hosts or "") if h.strip()}
    turns = []
    for line in full.splitlines():
        m = SPEAKER_LINE.match(line.strip())
        if m:
            h = int(m.group(1) or 0)
            turns.append((h * 3600 + int(m.group(2)) * 60 + int(m.group(3)),
                          m.group(4).strip()))
    if not turns:
        return ["逐字稿中找不到任何 `[MM:SS] 講者：` 格式的行，講者標記可能整份缺失"]

    # (0) 裸時間戳：有時間戳但整行沒有講者標記。PROMPT 明文要求每行都要有標籤，
    #     所以這是模型直接違規。08-07 的 MiB 有 71% 的行是這樣（使用者回報
    #     「1:00–1:19 整段無標記」），而完整度 1.00、狀態 OK，完全看不出來。
    stamped = sum(1 for l in full.splitlines() if re.match(r"^\s*\[\d", l))
    if stamped and len(turns) < 0.8 * stamped:
        out.append("有 %.0f%% 的行只有時間戳、沒有講者標記（%d／%d 行），"
                   "該段落的發言歸屬無法判定"
                   % (100.0 * (stamped - len(turns)) / stamped,
                      stamped - len(turns), stamped))

    names = [n for _, n in turns]
    uniq = sorted(set(names))
    # 泛稱可能帶前綴（`*Speaker 3`、`Male Speaker 1`），不能用行首錨定，
    # 否則它們會被歸進「真名」，同一個標籤在不同訊號裡身分互相矛盾。
    generic = {n for n in uniq if re.search(r"(speaker|announcer|unknown|host|guest)", n, re.I)}
    real = [n for n in uniq if n not in generic]

    # (1) 標籤本身就壞掉——把整句台詞、廣告文案或帶前綴的泛稱當成人名。
    #     **不要用「不在主持人名單裡」當訊號**：來賓本來就不在名單上，那樣會對
    #     每一集有來賓的節目誤報（實測 9 集報 8 集，等於沒有訊號）。
    def malformed(n):
        return (len(n.split()) > 4 or n.startswith(("*", "[", "-"))
                or "[" in n or re.search(r"\d", n)
                or re.match(r"^\W", n))
    bad = [n for n in real if malformed(n)]   # 泛稱本來就帶數字，不能拿來比對
    if bad:
        out.append("講者標記格式異常，疑似把台詞或廣告當成人名：%s"
                   % "、".join(bad[:4]))

    # (2) 只出現一個講者，但節目有多位主持人 → 多半是被合併了
    if len(uniq) == 1 and len(known) > 1:
        out.append("全集只有一個講者標記「%s」，但主持人名單有 %d 人，疑似多位講者被合併"
                   % (uniq[0], len(known)))

    # (3) 泛稱佔比過高卻又混著真名 → 同一集裡時而認得出時而認不出，歸屬不可靠。
    #     只有泛稱（全程 Speaker N）是誠實的，不報。
    gen_turns = sum(1 for n in names if n in generic)
    if generic and real and gen_turns >= 0.4 * len(names):
        out.append("泛稱標記佔 %.0f%%（%s）卻又混用真名（%s），講者歸屬不一致，引用發言前務必核對"
                   % (100.0 * gen_turns / len(names), "、".join(sorted(generic)[:3]),
                      "、".join(real[:4])))

    # (4) 單一講者連續獨佔過久。門檻取 15 分鐘：來賓講 10 分鐘在訪談節目很常見，
    #     但主持人連續 20 分鐘無人接話幾乎一定是標記整段錯置（08-07 的 MiB 與 20VC）。
    run_name, run_start = turns[0][1], turns[0][0]
    for t, n in turns[1:] + [(turns[-1][0] + 1, None)]:
        if n != run_name:
            if t - run_start >= 900 and len(uniq) > 1:
                out.append("「%s」自 %d:%02d 起連續發言約 %d 分鐘無人接話，"
                           "對談型節目不太合理，該段標記可能整段錯置"
                           % (run_name, run_start // 60, run_start % 60, (t - run_start) // 60))
            run_name, run_start = n, t
    return out


def rank_models(names, prefs, avoid_preview=True):
    scored = []
    for n in names:
        low = n.lower()
        if "gemini" not in low or any(t in low for t in _BAD_MODEL_TOKENS):
            continue
        score = 100.0
        for i, p in enumerate(prefs):
            if low.startswith(p.lower()):
                score = float(i)
                break
        else:
            for i, p in enumerate(prefs):
                if p.lower() in low:
                    score = i + 0.5
                    break
        if avoid_preview and ("preview" in low or "-exp" in low):
            score += 20
        if "pro" in low:
            score += 40
        scored.append((score, len(n), n))
    scored.sort()
    return [n for _, _, n in scored]


def probe_model(api_key, name):
    """送 0.6 秒真實音訊，同時確認三件事：
    (a) 模型對本專案開放、(b) 吃得下音訊、(c) 它接受哪一組 generationConfig。

    第 (c) 項一定要在這裡就探測好。2026-08-02 實測：gemini-3.5-flash 接受
    「maxOutputTokens 32768 ＋ thinkingBudget 0」，Flash-Lite 卻直接回 400，
    而且訊息只有通用的「Request contains an invalid argument.」，看不出是哪個欄位。
    先在探測階段用小額度試出可用組合，正式轉錄就不會浪費請求在試誤上。"""
    url = "%s/models/%s:generateContent" % (API_ROOT, name)

    def call(gc, timeout):
        body = {"contents": [{"parts": [
            {"text": "Reply with the single word OK."},
            {"inline_data": {"mime_type": "audio/mpeg", "data": _PROBE_MP3_B64}},
        ]}], "generationConfig": gc}
        return http_post_json(url, body, {"x-goog-api-key": api_key}, timeout=timeout)

    bad_arg = False
    for vi, gc in enumerate(gen_variants(MAX_OUTPUT_TOKENS)):
        probe_gc = dict(gc)
        probe_gc["maxOutputTokens"] = 64      # 探測時不需要長輸出
        for attempt in (1, 2):
            try:
                resp = call(probe_gc, 90 if attempt == 1 else 150)
                if not (resp.get("candidates") or []):
                    return False, "無回應內容", None
                MODEL_GENCFG[name] = gc
                note = "可處理音訊" if vi == 0 else "可處理音訊（%s）" % describe_cfg(gc)
                return True, note, gc
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                if e.code == 429:
                    _, _, per_day = parse_quota_error(raw)
                    if per_day:
                        return False, "今日額度已滿", None
                    time.sleep(8)
                    continue
                if e.code == 404:
                    return False, "未開放", None
                if e.code == 400:
                    bad_arg = True
                    break                      # 換下一組 generationConfig
                return False, "HTTP %s" % e.code, None
            except Exception as e:
                if attempt == 2:
                    return False, str(e)[:60], None
                time.sleep(5)                  # 逾時就再試一次
    return False, ("不接受任何參數組合" if bad_arg else "不支援音訊輸入"), None


def is_lite(name):
    return "lite" in name.lower()


def build_model_pool(api_key, cfg, state):
    """組模型輪替池。池子的「順序」就是實際使用順序（current_model 取第一個可用的）。

    免費層額度（2026-08-05 從 Console 實測，同一個專案內）：
        Flash 3.5／3.6                  5 RPM ／ 250K TPM ／  10 RPD  ← 08-05 從 20 砍半
        Flash 2.5                       5 RPM ／ 250K TPM ／  20 RPD
        Flash-Lite 2.5                 10 RPM ／ 250K TPM ／  20 RPD
        Flash-Lite 3.1／3.5            15 RPM ／ 250K TPM ／ 500 RPD  ← 50 倍

    **2026-08-05 起預設 Lite 優先**（`prefer_lite`，預設 True）。新版 Flash 只剩
    10 RPD，而重試（503 換模型前、字數不足、輸出截斷）會讓實際請求數放大約 2.5
    倍——08-05 實測 17 個預估請求打出 42 次，Flash 兩個模型雙雙超限（15/10、
    19/10），而 500 RPD 的 Lite 只用了 8 次。把稀缺資源放在最前面等於每天開場
    就燒光它。實測 Lite 的完整度 1.14–1.16，與 Flash 沒有可辨識的品質差距。

    要改回品質優先就把 config 的 `prefer_lite` 設為 false。
    """
    # **探測結果 72 小時內沿用（2026-08-10）。** 探測本身發真實的 generateContent、
    # 計入 RPD——每天 6–10 個請求，其中 3 個以上打在只有 10 RPD 的 Flash 池上，
    # 佔全日請求 25–30%，而結果早就存進 state 只是從不回讀。
    # 失效防線：404 會走 ModelUnavailable→EXHAUSTED；400 會沿 gen_variants 降參；
    # 若本次執行有模型 404（NOT_FOUND 非空），main() 會標 force_reprobe，隔天重測。
    cached = state.get("probe") or {}
    if (cached.get("pool") and not cached.get("force_reprobe")
            and time.time() - float(cached.get("ts", 0)) < 72 * 3600):
        MODEL_GENCFG.update(cached.get("gencfg") or {})
        pool = list(cached["pool"])
        state["model_pool"] = pool
        log("  沿用 %s 的模型探測結果（72 小時內免重測，省 6–10 個請求）"
            % time.strftime("%m-%d %H:%M", time.localtime(float(cached["ts"]))))
        return pool

    prefs = cfg.get("model_preference", ["gemini-3-flash", "gemini-flash", "flash"])
    avoid = bool(cfg.get("avoid_preview_models", True))
    order = rank_models(list_models(api_key), prefs, avoid)
    heavy = [n for n in order if not is_lite(n)]
    lite = [n for n in order if is_lite(n)]

    want_heavy = int(cfg.get("flash_slots", 3))
    want_lite = int(cfg.get("lite_slots", 3))
    pool, notes = [], []

    def take(cands, want, label):
        got = 0
        for name in cands:
            if got >= want or name in pool:
                continue
            okay, why, _ = probe_model(api_key, name)
            notes.append("%s（%s）" % (name, why))
            log("  測試 %s〔%s〕→ %s" % (name, label, why))
            if okay:
                pool.append(name)
                got += 1

    if bool(cfg.get("prefer_lite", True)):
        take(lite, want_lite, "Lite・高額度・主力")
        take(heavy, want_heavy, "Flash・備援")
    else:
        take(heavy, want_heavy, "Flash")
        take(lite, want_lite, "Lite・高額度")
    if not pool:
        raise RuntimeError("沒有任何可用模型。已測試：%s" % "；".join(notes))
    state["model_pool"] = pool
    state["probe"] = {"ts": time.time(), "pool": pool,
                      "gencfg": dict(MODEL_GENCFG)}
    return pool


# ---------------------------------------------------------------- 轉錄

PROMPT = """You are producing a VERBATIM transcript of one segment of a podcast, for use in a professional financial research digest.

Show: {show}
Episode: {title}
Speakers who MAY appear (not a guarantee - see rule 2c): {hosts}
Segment {idx} of {total} of the full episode.

Rules - follow all of them:
1. Transcribe EVERYTHING that is spoken. Do not summarise, paraphrase, condense, abridge, or skip any portion of the audio. Every sentence spoken must appear in your output. Completeness matters more than polish.
2. Start each speaker turn on a new line, formatted exactly as: [MM:SS] Speaker Name: text
   Timestamps MUST be relative to the start of THIS AUDIO FILE: the first line of
   your output is [00:00] or close to it, regardless of where this segment sits in
   the full episode. Do not offset them to the episode timeline - that is done
   afterwards by the caller, and doing it here produces a double offset.
   EVERY line must carry a speaker label - never emit a bare timestamp with no name.

   SPEAKER LABELLING - read this carefully, it is the part most often got wrong:

   a. The DEFAULT label is "Speaker 1", "Speaker 2", etc. Use a real name ONLY when
      you have positive evidence in the audio itself: the person introduces themselves
      ("I'm ..."), someone addresses them by name ("But Jason, ..."), or the host names
      them when handing over. Voice similarity or "this is probably the host" is NOT
      evidence.
   b. A WRONG NAME IS FAR WORSE THAN NO NAME. Downstream this transcript is used to
      attribute opinions and direct quotations to real, named people. "Speaker 2" is
      honest and harmless; the wrong name is a false statement about a real person and
      is very hard to detect later. When in doubt, use "Speaker N".
   c. The known-speaker list tells you who MIGHT appear, not who DOES. Hosts take
      episodes off, guests vary, and some listed hosts are absent entirely. Never
      assume a listed name is present just because it is on the list.
   d. Keep labels CONSISTENT within the segment. If you labelled a voice "Speaker 2"
      at 03:00, the same voice is "Speaker 2" at 15:00. Do not switch a voice from one
      name to another partway through, and do not renumber.
   e. Advertisements, sponsor reads, network station IDs and trailers are usually NOT
      the show's hosts. Label them "Announcer" (or the name they give themselves, e.g.
      "I'm Carol Massar") - never attribute them to a host just because they open the
      episode.
   f. On a two-person interview the host asks and the guest answers; you may use that
      to keep two voices apart, but it still does not license guessing their names.
3. This is a finance and technology show. Correct obvious mis-hearings of proper nouns from context - company names, ticker symbols, fund names, officials, and terms such as FOMC, basis points, Nasdaq, CPI, PCE.
4. Mark paid advertisement reads with [AD] at the start of that turn, but still transcribe them.
5. Output ONLY the transcript. No preamble, no headings, no closing remarks, no commentary about the audio.

Context that may help you resolve names (from the show notes):
{notes}
"""


def transcribe_one(api_key, model, file_uri, meta, idx, total, strict=False):
    prompt = PROMPT.format(
        show=meta["show"], title=meta["title"],
        hosts=meta["hosts"] or "(not known - use Speaker 1, Speaker 2, ...)",
        idx=idx + 1, total=total,
        notes=(meta.get("description") or "")[:800])
    if strict:
        prompt += ("\nIMPORTANT: a previous attempt returned a transcript that was far too "
                   "short, which means content was omitted. Transcribe the ENTIRE segment "
                   "from the first second to the last. Do not stop early.\n")

    variants = gen_variants(MAX_OUTPUT_TOKENS)
    gc = MODEL_GENCFG.get(model, variants[0])
    try:
        vi = variants.index(gc)
    except ValueError:
        vi = 0

    def make_body(g):
        return {"contents": [{"parts": [
            {"text": prompt},
            {"file_data": {"mime_type": "audio/mpeg", "file_uri": file_uri}},
        ]}], "generationConfig": g}

    body = make_body(gc)
    url = "%s/models/%s:generateContent" % (API_ROOT, model)
    headers = {"x-goog-api-key": api_key}

    last_err = None
    overload_tries = 0
    for retry in range(5):
        LIMITER.wait()
        try:
            resp = http_post_json(url, body, headers)
            break
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            last_err = "HTTP %s %s" % (e.code, raw[:200])
            if e.code == 400 and vi + 1 < len(variants):
                vi += 1
                gc = variants[vi]
                MODEL_GENCFG[model] = gc
                log("    %s 不接受該參數組合，改用 %s" % (model, describe_cfg(gc)))
                body = make_body(gc)
                continue
            if e.code == 429:
                delay, metric, per_day = parse_quota_error(raw)
                if per_day:
                    log("    %s 今日額度已滿（%s）" % (model, metric[:60]))
                    raise DailyQuotaForModel(model)
                delay = delay or min(120, 20 * (2 ** retry))
                log("    限流（%s），等待 %d 秒" % (metric[:50] or "RPM/TPM", delay))
                time.sleep(delay)
                continue
            if e.code == 404:
                raise ModelUnavailable(raw[:200])
            if e.code in (500, 503):
                # 短暫過載給兩次機會就換模型。不要在同一個模型上把重試燒完：
                # 重試也計入 RPD，而池子裡的 Lite 通常還有幾百次額度閒著。
                overload_tries += 1
                if overload_tries >= 2:
                    raise ModelOverloaded("HTTP %s 連續 %d 次" % (e.code, overload_tries))
                time.sleep(10)
                continue
            raise RuntimeError(last_err)
        except (DailyQuotaForModel, ModelUnavailable, ModelOverloaded):
            raise
        except Exception as e:
            last_err = str(e)
            time.sleep(15 * (retry + 1))
    else:
        raise RuntimeError("重試多次仍失敗：%s" % last_err)

    cands = resp.get("candidates") or []
    if not cands:
        raise RuntimeError("回應沒有 candidates：%s" % json.dumps(resp)[:200])
    cand = cands[0]
    parts = (cand.get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts).strip(), cand.get("finishReason", "")


def transcribe_episode(api_key, pool, ep, cfg, workdir):
    # **單集牆鐘上限，整集只設一次**（2026-08-10 修正語意）。
    # 舊版把 deadline 設在「每段、每次 attempt」裡，等於 2 小時集＝6 段×2 次
    # 各領一份 20 分鐘、理論最壞 4 小時，而且只在過載分支檢查——名為單集上限、
    # 實為無上界。乾淨跑永遠不會觸發，所以一直沒被發現。
    # 值也同步從 1200 加大到 3600：2 小時集乾淨跑要 10–20 分鐘，1200 秒在
    # 集層級語意下會把本來會成功的集殺成 FAILED（TIP 週日集每週固定陣亡一次）。
    ep_deadline = time.time() + int(cfg.get("episode_budget_seconds", 3600))
    seg = int(cfg.get("segment_seconds", 1200))
    max_bytes = int(cfg.get("max_chunk_mb", 48)) * 1024 * 1024
    mp3 = os.path.join(workdir, "src.mp3")
    log("  下載音檔…")
    size = download(ep["audioUrl"], mp3)
    log("  下載完成 %.1f MB，開始切段…" % (size / 1e6))
    chunkdir = os.path.join(workdir, "chunks")
    os.makedirs(chunkdir, exist_ok=True)
    chunks, how = split_audio(mp3, chunkdir, seg, max_bytes)
    total = len(chunks)
    starts, acc = [], 0.0
    for _, d in chunks:
        starts.append(acc)
        acc += d
    log("  切成 %d 段（%s），總長 %.0f 分 → 本集需 %d 個請求"
        % (total, how, acc / 60.0, total))

    cdir = os.path.join(CACHE_DIR, str(ep["trackId"]))
    os.makedirs(cdir, exist_ok=True)
    results, per_chunk, warnings = [], [], []
    wpm = float(ep.get("wpm") or WORDS_PER_MIN)   # 該節目的語速基準
    loop_segs = set()          # 哪幾段出現跳針。spoken_words() 會把跳針扣掉，
                               # 段級語速檢查因此看不到它，位置資訊要在這裡留住。

    def current_model():
        """挑第一個可用的模型。

        兩種不可用要分清楚，否則會出 2026-08-06 那種事：
          EXHAUSTED  日額度用盡或 404 → **本次執行永久除名**，跨集共用不必重撞
          OVERLOADED 500／503 暫時過載 → **只冷卻一段時間**，到期自動回池

        把 503 也丟進 EXHAUSTED 的後果：08-06 三個 500 RPD 的 Lite 在 77 秒內
        被一次過載尖峰全部永久除名，剩下 10 RPD 的 Flash 扛完整場，直接把
        Flash 燒到 22/10。暫時性錯誤不可以產生永久性後果。
        """
        now = time.time()
        for m in pool:
            if m in EXHAUSTED:
                continue
            if OVERLOADED.get(m, 0) > now:
                continue
            return m

        # 全部都在冷卻中（而非真的用完）→ 等最早到期的那個
        cooling = [(t, m) for m, t in OVERLOADED.items()
                   if t > now and m not in EXHAUSTED and m in pool]
        if cooling:
            t, m = min(cooling)
            wait = min(120, max(1, int(t - now) + 1))
            log("    池內模型全在冷卻中，等 %d 秒後回到 %s" % (wait, m))
            time.sleep(wait)
            return current_model()
        raise QuotaExhausted("所有模型的今日額度都用完了")

    for i in range(total):
        path, dur = chunks[i]
        cpath = os.path.join(cdir, "part_%03d.txt" % i)
        expected = max(60.0, dur) / 60.0 * wpm
        if os.path.exists(cpath) and os.path.getsize(cpath) > 200:
            with open(cpath, "r", encoding="utf-8") as f:
                text = f.read()
            n = spoken_words(text)
            # **快取也要過品質門檻（2026-08-10）。** 舊版只驗「>200 bytes」，
            # 被截斷的壞段一旦進了 cache，下次接續時會被無條件吸收——該段內容
            # 永久缺失且無徵兆。門檻沿用與現場轉錄相同的 0.55×。
            # **只丟棄一次**：丟棄時留 .redo 標記，下次再讀到（表示重轉過一次
            # 還是低於門檻）就照收——否則語速慢於基準的節目會每天重轉同一段，
            # 反覆燒 RPD 直到額度死光（wpm 校準偏高時的最壞情況）。
            redo_mark = cpath + ".redo"
            if n < expected * 0.55 and not os.path.exists(redo_mark):
                log("    第 %d/%d 段快取僅 %d 字（預期約 %d），丟棄重轉一次"
                    % (i + 1, total, n, int(expected)))
                with open(redo_mark, "w") as f:
                    f.write("discarded %d words at %s\n" % (n, time.strftime("%F %T")))
                os.remove(cpath)
            else:
                if collapse_loops(_TURN_PREFIX.sub("", text))[1]:
                    loop_segs.add(i)
                if n < expected * 0.55:
                    warnings.append("第 %d/%d 段僅 %d 字，遠低於預期 %d（快取重轉後仍不足）"
                                    % (i + 1, total, n, int(expected)))
                results.append(text)
                per_chunk.append((i, dur, n))
                log("    第 %d/%d 段 %d 字（快取）" % (i + 1, total, n))
                continue

        # 集層級時限：**每段開始前檢查一次**，不再於段內重設。
        if time.time() > ep_deadline:
            raise RuntimeError(
                "單集耗時超過 %d 秒上限，於第 %d/%d 段前中止；"
                "已完成段落留在快取，下次執行接續"
                % (int(cfg.get("episode_budget_seconds", 3600)), i + 1, total))
        text, n = "", 0
        for attempt in (1, 2):
            uri = name = None
            try:
                log("    第 %d/%d 段上傳中（%.1f MB）…"
                    % (i + 1, total, os.path.getsize(path) / 1e6))
                uri, name = upload_file(api_key, path)
                # 輪換要同時受「次數」與「時間」約束。503 改成「只冷卻不除名」
                # 之後，若供應端持續過載，本段會在池內無限輪轉，唯一的自然終點
                # 是把當天所有額度燒到 429。時間約束用的是**集層級的 ep_deadline**
                # （2026-08-10 前這裡每段每 attempt 重設一份，等於沒有上限）。
                max_rot = max(4, len(pool) * 3)
                overload_rotations = 0   # 只計過載輪換，不要和額度輪換混用同一個計數器
                seg_t0 = time.time()     # 只供錯誤訊息回報實際耗時，不參與判斷
                while True:
                    m = current_model()
                    try:
                        text, finish = transcribe_one(
                            api_key, m, uri, ep, i, total, strict=(attempt > 1))
                        break
                    except ModelOverloaded as e:
                        # 暫時性：只冷卻，不除名。到期自動回池。
                        cool = int(cfg.get("overload_cooldown_seconds", 300))
                        OVERLOADED[m] = time.time() + cool
                        overload_rotations += 1
                        if overload_rotations >= max_rot or time.time() > ep_deadline:
                            raise RuntimeError(
                                "全池持續過載，輪換 %d 次／本段耗時 %.0f 分仍失敗：%s"
                                % (overload_rotations,
                                   (time.time() - seg_t0) / 60.0,
                                   str(e)[:60]))
                        log("    %s 暫時過載，冷卻 %d 秒（%s）"
                            % (m, cool, str(e)[:40]))
                    except (DailyQuotaForModel, ModelUnavailable) as e:
                        # 永久性：本次執行不再使用。額度輪換次數天然受限於池子
                        # 大小，不需要也不應該計入過載上限。
                        EXHAUSTED.add(m)
                        if isinstance(e, ModelUnavailable):
                            NOT_FOUND.add(m)   # 探測快取失效訊號，main() 收尾時會處理
                        # 只看 EXHAUSTED 會把冷卻中的模型也報成「改用」，
                        # 事後靠日誌反推根因時會被誤導（08-06 就是這樣查的）。
                        nxt = [x for x in pool if x not in EXHAUSTED
                               and OVERLOADED.get(x, 0) <= time.time()]
                        if not [x for x in pool if x not in EXHAUSTED]:
                            raise QuotaExhausted("所有模型的今日額度都用完了")
                        log("    %s 本次停用（%s），改用 %s"
                            % (m, str(e)[:40], nxt[0] if nxt else "（全池冷卻中，等待）"))
            finally:
                delete_file(api_key, name)
            n = spoken_words(text)
            if collapse_loops(_TURN_PREFIX.sub("", text))[1]:
                loop_segs.add(i)
            truncated = (finish == "MAX_TOKENS")
            if attempt == 2:
                if truncated:
                    warnings.append("第 %d/%d 段輸出被 token 上限截斷（重試後仍是）"
                                    % (i + 1, total))
                elif n < expected * 0.55:
                    warnings.append("第 %d/%d 段僅 %d 字，遠低於預期 %d（重試後仍不足）"
                                    % (i + 1, total, n, int(expected)))
                break
            # 截斷或明顯過短都要重試。Lite 模型有 500 RPD，重試成本已經不高。
            if truncated:
                log("    第 %d 段被 token 上限截斷（%d 字），重試一次" % (i + 1, n))
                continue
            if n >= expected * 0.55:
                break
            log("    第 %d 段僅 %d 字（預期約 %d），重試一次" % (i + 1, n, int(expected)))
        if text:
            with open(cpath, "w", encoding="utf-8") as f:
                f.write(text)
        results.append(text)
        per_chunk.append((i, dur, n))
        log("    第 %d/%d 段完成，%d 字（%.0f 字/分）"
            % (i + 1, total, n, n / max(1.0, dur / 60.0)))

    # --- 品質檢查：絕對值（vs 本節目基準）＋ 相對值（vs 本集中位數）---
    rates = [n / (d / 60.0) for _, d, n in per_chunk if d > 60 and n > 0]
    median_rate = statistics.median(rates) if rates else wpm
    for i, d, n in per_chunk:
        if d <= 60:
            continue
        rate = n / (d / 60.0)
        if rate < REL_RATIO * median_rate:
            warnings.append("第 %d/%d 段語速僅 %.0f 字/分，為本集中位數 %.0f 的 %.0f%%，可能有缺漏"
                            % (i + 1, total, rate, median_rate, 100 * rate / median_rate))
        elif rate > HIGH_RATIO * median_rate:
            warnings.append("第 %d/%d 段語速高達 %.0f 字/分，為本集中位數 %.0f 的 %.0f%%，"
                            "疑似重複跳針（LLM 在長音檔上的典型失敗）"
                            % (i + 1, total, rate, median_rate, 100 * rate / median_rate))

    full = "\n\n".join(offset_timestamps(t, starts[i])
                        for i, t in enumerate(results) if t)
    words = spoken_words(full)
    seconds = acc if acc > 0 else (ep["durationMs"] / 1000.0)
    expected_total = max(1, int(seconds / 60.0 * wpm))
    ratio = words / float(expected_total)
    if ratio < MIN_RATIO:
        # 基準值一律引用變數，不要寫死數字——這句會進 front matter
        # 與 manifest，寫死的話改了常數就會對使用者報一個錯的基準（曾發生）。
        warnings.append("全集字數 %d 僅為 %d 字/分基準的 %.0f%%"
                        % (words, wpm, ratio * 100))

    # 講者訊號**不併進 warnings**。`warnings` 會直接決定 status，而 DEGRADED 的
    # 定義是「完整度不足」——把講者問題混進去會讓完整度正常的集數被標成降級，
    # 理由還是錯的（2026-08-07 實測：九集會有五集誤降，而唯一真正標錯人的
    # All-In 反而零訊號）。兩者是不同維度，分開走。
    _, dropped = collapse_loops(_TURN_PREFIX.sub("", full))
    if dropped:
        where = ("；集中在第 %s 段" % "、".join(str(i + 1) for i in sorted(loop_segs))
                 if loop_segs else "")
        warnings.append("偵測到跳針重複，已從字數統計剔除 %s 字%s。"
                        "**跳針處的實際內容是缺的**，摘譯時不要當成有內容"
                        % (f"{dropped:,}", where))

    # 整段複製：跟上面的 collapse_loops **問的是不同的問題**。
    # 前者抓「同一個 token 連著跳針」，這條抓「一整段連貫文字被放了兩次」。
    # 2026-08-21 的 tip 有 172 與 152 token 的整段複製，collapse_loops 一處都沒看到，
    # 於是那一集被判 OK 送進撰寫階段 —— **子代理會把重播那段當成有內容照寫。**
    for r in significant_repeats(full, _ANCHORS["block_repeat_shingle"],
                                 _ANCHORS["block_repeat_min_tokens"],
                                 _ANCHORS["block_repeat_coldopen_head"]):
        warnings.append("偵測到整段複製 %d token（第 %d → 第 %d 個字）。"
                        "**重播若覆蓋掉原內容，那段就真的不見了**，"
                        "而完整度指不出來——摘譯時不要把重播段當成有內容"
                        % (r["tokens"], r["first"], r["second"]))

    speaker_notes = check_speaker_labels(full, ep.get("hosts", ""))
    ts_notes = check_timestamps(full, seconds, ratio)
    status = "OK" if not warnings else "DEGRADED"
    return (full, words, expected_total, ratio, median_rate, status, warnings,
            total, speaker_notes, ts_notes)


# ---------------------------------------------------------------- 主流程

def main():
    cfg = load_json(CONFIG_PATH, {})
    shows = load_json(SHOWS_PATH, {})
    state = load_json(STATE_PATH, {})
    if not cfg:
        # **config 壞損必須中止，不能靜默退回程式預設值（2026-08-10）。**
        # 舊行為：load_json 失敗回 {}，所有參數退回內建預設——而內建預設裡
        # 曾有 segment_seconds=1800 這種「被回滾過的值」。用錯參數跑完一天
        # 比不跑更難發現；不跑會被 healthcheck 的日誌檢查抓到。
        log("config.json 讀不到或解析失敗，中止（不要用內建預設值靜默硬跑）。")
        return 2
    if not shows:
        log("找不到 shows.json，中止。")
        return 2
    try:
        with open(KEY_PATH, "r", encoding="utf-8") as f:
            api_key = f.read().strip()
    except Exception:
        log("找不到 API key（%s），中止。" % KEY_PATH)
        return 2
    if not api_key:
        log("API key 是空的，中止。")
        return 2

    global LIMITER, MAX_OUTPUT_TOKENS
    LIMITER = RateLimiter(float(cfg.get("min_request_interval_seconds", 10)))
    MAX_OUTPUT_TOKENS = int(cfg.get("max_output_tokens", 32768))

    # **整場執行的牆鐘上限（2026-08-10）**：從程式啟動就起算，02:40 之後不再
    # 「開始」新的集數。**必須設在 discover 與模型探測之前**——重新探測的那一天
    # （最慢的一天）會多花十幾分鐘，若在探測後才起算，門檻會往後漂，而這個機制
    # 存在的理由正是「03:00 日報不能讀到不完整的 manifest」。
    # 已在跑的那一集由 episode_budget 管，不會被中途腰斬。
    run_deadline = time.time() + int(cfg.get("run_budget_seconds", 6000))

    now = dt.datetime.now(dt.timezone.utc)
    max_h = int(cfg.get("max_lookback_hours", 72))
    last = state.get("last_run_utc")
    if last:
        since = dt.datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc) - dt.timedelta(minutes=30)
    else:
        since = now - dt.timedelta(hours=int(cfg.get("default_window_hours", 48)))
    floor = now - dt.timedelta(hours=max_h)
    if since < floor:
        log("距離上次執行超過 %d 小時，視窗截斷在 %d 小時內。" % (max_h, max_h))
        since = floor

    seen = {e["trackId"] for e in state.get("seen", [])}
    log("視窗：%s → %s (UTC)" % (since.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M")))

    priority = cfg.get("show_priority", [])
    eps, newest = discover(shows, since, seen, priority)
    if not eps:
        # ---- 0 集這條路徑在 2026-08-15 出過一次事，兩個獨立的修正都在這裡 ----
        #
        # ① 健全性對照（零額外請求，用 discover 已抓回的資料）。
        #    「23 檔全部同時安靜超過 stale_hours」在現實中不會發生——其中有每個
        #    交易日都發的 Bloomberg。真發生就是查詢壞了，不是真的沒節目。
        #    08-15 那天這個數字是 15 天（iTunes 回了整份 07-31 的過期快取）。
        stale_h = int(cfg.get("stale_feed_hours", 72))
        stale = newest is None or (now - newest).total_seconds() > stale_h * 3600
        if stale:
            age = "查無任何集數" if newest is None else \
                  "%.1f 天前" % ((now - newest).total_seconds() / 86400.0)
            log("!! 可疑的 0 集：全部 %d 檔節目裡最新的一集是 %s（門檻 %d 小時）。"
                % (len(shows), age, stale_h))
            log("!! 這比較像 iTunes 快取過期或網路異常，不像真的沒有新節目。"
                "**已保留視窗起點**，下次執行會重新涵蓋這段時間。")
            log("!! 人工覆核：對同一支 AppleID 帶與不帶 &cb= 各查一次比對。")
        #
        # ② **0 集一律不推進 `last_run_utc`。**
        #    舊版無條件推進，於是任何一次「查詢暫時失敗」都會被固化成永久缺口
        #    ——08-15 就這樣讓 10 集落在窗外，只能靠人工回捲 state 救回。
        #    代價已經算過，是零：視窗最多長到 max_lookback_hours（72 小時）就被
        #    截斷，而 `seen` 保留 30 天，不會重抓舊集數；查詢次數與視窗無關
        #    （視窗只做過濾）。**真 0 集日唯一的變化是明天視窗變寬，沒有成本。**
        log("沒有新集數。（不推進 last_run_utc，下次視窗仍從 %s 起算）"
            % since.strftime("%m-%d %H:%M"))
        save_json(STATE_PATH, state)
        return 0

    total_min = sum(e["durationMs"] for e in eps) / 60000.0
    seg_min = int(cfg.get("segment_seconds", 1200)) / 60
    log("找到 %d 集，總長 %.0f 分鐘，預估約 %d 個請求。"
        % (len(eps), total_min, -(-int(total_min) // int(seg_min))))
    log("處理順序（依日報優先序）：%s" % "、".join(e["showKey"] for e in eps))

    tz = dt.timezone(dt.timedelta(hours=8))
    daydir = os.path.join(os.path.expanduser(cfg.get("output_dir", "~/podcast-transcripts")),
                          dt.datetime.now(tz).date().isoformat())
    os.makedirs(daydir, exist_ok=True)

    pool = build_model_pool(api_key, cfg, state)
    save_json(STATE_PATH, state)
    log("模型輪替池（每個各有獨立日額度）：%s" % "、".join(pool))

    manifest, quota_stop = [], False
    for ep in eps:
        stop_reason = None
        if quota_stop:
            stop_reason = "今日額度用完，本集未處理"
        elif time.time() > run_deadline:
            stop_reason = ("整場執行超過 %d 秒上限，本集未開始（日報 03:00 要讀 "
                           "manifest，不能再拖）" % int(cfg.get("run_budget_seconds", 6000)))
        if stop_reason:
            manifest.append({"showKey": ep["showKey"], "show": ep["show"],
                             "title": ep["title"], "releaseDate": ep["releaseDate"],
                             "durationMs": ep["durationMs"], "appleUrl": ep["appleUrl"],
                             "status": "FAILED", "error": stop_reason})
            continue
        log("── %s｜%s（%.0f 分）"
            % (ep["show"], ep["title"][:60], ep["durationMs"] / 60000.0))
        fname = "%s-%s.md" % (ep["showKey"], ep["trackId"])
        entry = {"showKey": ep["showKey"], "show": ep["show"], "title": ep["title"],
                 "releaseDate": ep["releaseDate"], "durationMs": ep["durationMs"],
                 "appleUrl": ep["appleUrl"], "file": fname}
        workdir = tempfile.mkdtemp(prefix="podfetch-")
        try:
            (text, words, expected, ratio, median_rate,
             status, warns, nseg, spk, tsn) = transcribe_episode(
                api_key, pool, ep, cfg, workdir)
            head = ["---",
                    "show: %s" % ep["show"],
                    "showKey: %s" % ep["showKey"],
                    "title: %s" % ep["title"].replace("\n", " "),
                    "released_utc: %s" % ep["releaseDate"],
                    "duration_ms: %d" % ep["durationMs"],
                    "apple_url: %s" % ep["appleUrl"],
                    "source: Gemini API 語音轉錄",
                    "segments: %d" % nseg,
                    "words: %d" % words,
                    "expected_words: %d" % expected,
                    "words_per_minute: %.0f" % median_rate,
                    "completeness: %.2f" % ratio,
                    "status: %s" % status]
            if warns:
                head.append("warnings:")
                head += ["  - %s" % w for w in warns]
            # 講者訊號獨立一欄，不影響 status。摘譯時要讀它來決定哪幾段的
            # 發言歸屬需要靠上下文覆核。
            if spk:
                head.append("speaker_notes:")
                head += ["  - %s" % s for s in spk]
            # 時間軸訊號也獨立一欄，理由與 speaker_notes 相同：它不是「內容不足」，
            # 不該影響 status；但摘譯時必須看得到，因為它決定章節怎麼切。
            if tsn:
                head.append("timestamp_notes:")
                head += ["  - %s" % s for s in tsn]
            head.append("---")
            with open(os.path.join(daydir, fname), "w", encoding="utf-8") as f:
                f.write("\n".join(head) + "\n\n" + text + "\n")
            entry.update(status=status, words=words,
                         completeness=round(ratio, 2), warnings=warns,
                         speakerNotes=spk, timestampNotes=tsn)
            log("  → %s（%s，%d 字，%.0f 字/分，完整度 %.0f%%%s%s）"
                % (fname, status, words, median_rate, ratio * 100,
                   "，講者標記 %d 則待覆核" % len(spk) if spk else "",
                   "，時間軸 %d 則待覆核" % len(tsn) if tsn else ""))
            shutil.rmtree(os.path.join(CACHE_DIR, str(ep["trackId"])), ignore_errors=True)
        except QuotaExhausted as e:
            entry.update(status="FAILED", error=str(e)[:200])
            quota_stop = True
            log("  ✗ %s" % e)
            log("    已完成的段落留在 %s，下次執行直接沿用、不重跑。" % CACHE_DIR)
        except Exception as e:
            entry.update(status="FAILED", error=str(e)[:400])
            log("  ✗ 失敗：%s" % e)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        manifest.append(entry)
        if entry.get("status") != "FAILED":
            seen.add(ep["trackId"])

    save_json(os.path.join(daydir, "manifest.json"), {
        "generatedAt": dt.datetime.now(tz).isoformat(),
        "windowStartUtc": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windowEndUtc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": pool,
        "episodes": manifest,
    })

    cutoff = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    known = {e["trackId"] for e in state.get("seen", [])}
    kept = [e for e in state.get("seen", []) if e.get("at", "") >= cutoff]
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for e in eps:
        if e["trackId"] in seen and e["trackId"] not in known:
            kept.append({"trackId": e["trackId"], "at": stamp})
    state["seen"] = kept

    failed = [m for m in manifest if m.get("status") == "FAILED"]
    if failed:
        if last:
            state["last_run_utc"] = last
        log("有 %d 集未完成，保留原視窗起點，下次執行會自動接續。" % len(failed))
    else:
        state["last_run_utc"] = stamp
    if NOT_FOUND:
        # 沿用中的探測快取裡有模型 404 了——快取已過期，隔天強制重測全池。
        state.setdefault("probe", {})["force_reprobe"] = True
        log("模型 %s 已下架（404），已標記隔天重新探測。" % "、".join(sorted(NOT_FOUND)))
    save_json(STATE_PATH, state)

    ok = sum(1 for m in manifest if m.get("status") == "OK")
    log("完成：%d/%d 集正常。輸出目錄 %s" % (ok, len(manifest), daydir))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
