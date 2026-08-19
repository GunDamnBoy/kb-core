"""看門狗的檢查——跑在 Mac 上，看的是「哨兵還活著嗎」。

## 為什麼這一組非得在 GitHub 外面跑

GitHub 官方文件：public repo「no repository activity has occurred in 60 days」
時排程 workflow 會被自動停用，而且**沒有官方 opt-out**。

於是有一個共模失效：管線停了 → repo 沒有新 commit → 60 天後 GitHub 把哨兵也
關掉 → 從此連叫都不會叫。**看守者跟被看守的東西綁在同一個開關上，而且正好在
事情已經出問題的時候一起死。**

再開第二個 workflow 互看沒用——同一個開關會把兩個一起關掉。Mac 有效，是因為它
**不在 GitHub 那個開關的管轄範圍內**，而且 launchd 每天都會醒。

於是互看：**Actions 看資料新不新，Mac 看 Actions 還活著沒有。**

## 剩下的洞（明文，不假裝沒有）

Mac 關機 ＋ Actions 停掉 —— 沒有任何東西會發現。不接外部服務就解不掉。
接 healthchecks.io 那類 dead man's switch 可以補，代價是多一個帳號跟一個 secret。

payload 形狀：{"now": ISO8601, "heartbeat": {...}|None}
"""
import datetime as dt

from kbcore.check import Check, fail, ok, register, warn

MAX_HEARTBEAT_AGE_H = 30


def _sentinel_alive(p):
    hb = p.get("heartbeat")
    if hb is None:
        return fail("讀不到哨兵的 heartbeat —— 它可能從沒跑過、被 GitHub 停用了、"
                    "或 repo 沒同步。**「沒有壞消息」不等於「沒事」**")
    age = (dt.datetime.fromisoformat(p["now"])
           - dt.datetime.fromisoformat(hb["at"])).total_seconds() / 3600
    if age > MAX_HEARTBEAT_AGE_H:
        return fail(f"哨兵最後一次執行是 {hb['at']}，已經 {age:.0f} 小時 "
                    f"（上限 {MAX_HEARTBEAT_AGE_H}）—— 看守者自己死了")
    return ok()


register(Check(
    id="watch.sentinel_alive",
    covers=f"哨兵在 {MAX_HEARTBEAT_AGE_H} 小時內執行過",
    blind_to=[
        "哨兵有跑但每次都在同一個地方壞掉、只是壞得很準時",
        "heartbeat 是舊的但被別的東西重新 commit 了一次（時間戳來自 commit 而非執行）",
        "Mac 自己關機時，這條檢查連跑都沒跑——它看不見自己的缺席",
    ],
    run=_sentinel_alive,
    fixture={"now": "2026-08-19T01:00:00+00:00", "heartbeat": None},
    suite="watch",
))


def _sentinel_verdict(p):
    """哨兵活著但一直在叫，也是一種要被看見的狀態。

    主要通報管道是 GitHub issue；這條是本機的第二個出口，用在 issue 沒被看到
    的時候。它刻意只回 WARN——重複通報同一件事應該比原本那件事更小聲。
    """
    hb = p.get("heartbeat")
    if hb is None:
        return ok()
    code = hb.get("exit")
    if code:
        return warn(f"哨兵上一次執行回 exit {code}：{hb.get('summary', '（無摘要）')}")
    return ok()


register(Check(
    id="watch.sentinel_verdict",
    covers="哨兵上一次執行的判定是綠的",
    blind_to=[
        "哨兵判綠，但它自己的檢查有盲區（盲區是遞迴的）",
    ],
    run=_sentinel_verdict,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "heartbeat": {"at": "2026-08-19T00:00:00+00:00", "exit": 10,
                           "summary": "資料停在三天前"}},
    suite="watch",
))
