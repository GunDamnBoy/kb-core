"""資料 repo 的身分辨識——「我現在站在哪裡」。

2026-08-19 的事故教的：不可改寫守衛檢查的維度是**檔案**，它從設計上就看不見
「我站在哪個 repo」。所有破壞性動作都要問同一個問題——我驗證的是**物件**，
還是**我所在的位置**？前者永遠答不出後者。

這段刻意放在 kbcore 而不是 publish.py 裡：publish 要用它，哨兵的看門狗也要用。
守衛複製成兩份就是**雙軌漂移**的起點——改了一邊忘了另一邊，而且沒有任何訊號。
"""
import json
import os
from pathlib import Path

MARKER = ".kb-data-repo"


def day_json(doc) -> str:
    """日檔（`data/<日期>.json`）的**正規序列化**——這是它唯一的家。

    2026-08-29 的事故教的：`publish.py` 的不可改寫守衛比的是
    `target.read_text() != json.dumps(draft, ensure_ascii=False, indent=1)`，
    而 `render_day.py`／`build_series.py`／`rebuild_option.py` 三支全部寫
    `separators=(",", ":")`。**同一份文件因此有兩種寫法，而守衛比的是字串。**

    症狀是：任何一輪只要在同一台機器上先出圖再交草稿，
    第一次回執**必然**是 exit 11「已存在且內容不同」——
    而 exit 11 的字面意思是「已發布的一期就是已發布的樣子」，
    於是下一個人會被推去掛一份根本不需要的 errata。
    2026-08-29 那一輪就是這樣：`data/index.json` 當時根本沒有那一天、
    回執的 commit 是空字串，**那份日檔從來沒有被發布過**，
    逐行 diff 出來的差異只有一個 `window.to` 欄位。

    **`rebuild_option.py` 是更糟的那一個**：它是修既有封存的唯一合法工具，
    卻會把一份已發布的 `indent=1` 檔整份改寫成 compact ——
    資料一個位元都沒變，而 diff 是全檔重寫，**真正改了什麼因此看不見**。

    格式選 `indent=1` 不是美學：**publish 是最後寫入者，它決定了磁碟上的樣子**，
    所以其餘三支要向它靠攏，不是反過來。改這個函式等於改所有已發布檔的
    未來格式，改之前先想清楚既有封存怎麼辦（它們不改寫）。
    """
    return json.dumps(doc, ensure_ascii=False, indent=1)


def write_day_json(path, doc) -> int:
    """把日檔原子寫入 `path`，回傳寫了幾個位元組。

    **原子寫入不是選配。** 三支 `kbpublish.*` 每 60 秒掃一次 outbox 與 repo，
    非原子的寫入會讓它們讀到寫到一半的 JSON——而那個失敗是隨機出現的。
    """
    body = day_json(doc)
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, p)
    return len(body.encode("utf-8"))


def git_failure_detail(returncode: int, argv, stderr: str = "",
                       stdout: str = "", limit: int = 400) -> str:
    """把一次失敗的 git 呼叫寫成**回執讀得懂的一句話**。

    2026-09-16 的事故教的：`git` 這支程式在 Mac 上對**每一個**子指令回 exit 69
    （`/usr/bin/git` 是 Xcode CLT 的 xcrun shim，developer path 失效時就這樣），
    而三支 `kbpublish` 與 `kbcorepush` 全部失效了一天多。

    **它藏住的方式有兩層，而兩層都跟這個函式有關。**

    第一層：`tools/publish.py` 的 `git()` 用 `capture_output=True, check=True`，
    於是 git 自己的 stderr 被裝進 `CalledProcessError.stderr` **而沒有任何人讀它**。
    日誌裡只剩一個 traceback 與「returned non-zero exit status 69」——
    **診斷所需的那一行字一直都在物件上，只是從來沒有被取出來。**

    第二層：`tools/push_kbcore.py` 的 `git()` 預設 `check=False`，於是
    `git status --porcelain` 回 69、stdout 空 → `dirty=False`、`ahead=0`
    → 它每 300 秒印一次「kb-core 乾淨且未領先 origin —— 空輪次，不是失敗」。
    **git 全掛與「沒事做」在那支的輸出上長得一模一樣**，印了一天多。

    所以這個函式只有一件事要做得對：**把 stderr 放進回執**。
    分類、猜原因、給修法都不是它的工作——那些會過期，stderr 不會。

    `limit` 是截斷長度：回執要留得住、也要讀得完，而 git 偶爾會吐一整段建議。
    截斷時明寫「截斷」，**不要安靜地砍掉**（否則下一個人會以為 git 只說了這麼多）。
    """
    # `CalledProcessError.cmd` 帶著整條 argv（開頭就是 `git`），而這裡自己也要印
    # 一個 `git`。不正規化的話回執會寫成 `git git -C …` —— 不影響判讀，
    # 但那種小髒汙會讓人懷疑訊息是拼出來的，而這一句話的用途正是被相信。
    parts = [str(a) for a in (argv or [])]
    if parts and parts[0].rsplit("/", 1)[-1] == "git":
        parts = parts[1:]
    cmd = " ".join(parts)
    err = (stderr or stdout or "").strip()
    if len(err) > limit:
        err = err[:limit] + " …（截斷，完整內容在 stderr）"
    said = f"；git 說：{err}" if err else (
        "；**git 一個字都沒說** —— 那本身就是線索：git 自己的錯誤一定會寫 stderr，"
        "所以沉默多半代表 git 這支程式根本沒跑起來（找不到、被包在壞掉的 shim 裡、"
        "或執行環境不給跑）")
    return (f"`git {cmd}` 回 exit {returncode}{said} —— **重跑不會好，要人看**。"
            "第一件事是拿同一行去問另一個 repo：**也失敗就壞的是 git 這支程式或它的"
            "執行環境，不是這個 repo**（2026-09-15 起三個 repo 同時卡住就是這一種）。")


def check_destination(repo: Path, system_id: str) -> str:
    """回傳錯誤訊息；空字串表示通過。"""
    marker = Path(repo) / MARKER
    if not marker.exists():
        return f"{repo} 沒有 {MARKER} —— 它不是一個資料 repo，拒絕動作"
    got = marker.read_text().strip()
    if got != system_id:
        return f"{MARKER} 是 {got!r}，但呼叫指定的是 {system_id!r} —— 目的地不符，拒絕動作"
    return ""
