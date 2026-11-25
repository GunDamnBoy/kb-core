#!/usr/bin/env python3
"""在固定時刻**主動觸發**資料 repo 的哨兵（workflow_dispatch），不等 GitHub 自己的排程。

用法：dispatch_sentinel.py [repo ...]　（預設 chart-of-the-day；owner 固定 GunDamnBoy）

## 為什麼有這一支（2026-11-25）

`chart-of-the-day/.github/workflows/sentinel.yml` 排在 `20 7 * * *`（台北 15:20），
它的 `MAX_DATE_AGE_H` 就是照「15:20 跑」算的：今天這一期 ≤15 小時→綠、昨天那一期 39 小時→紅，
問的是「**今天這一期出來了沒**」。

**而它實際上從來沒有在 15:20 跑過。** 2026-11-11 至 11-24 的十四次排程執行，
建立時刻落在 UTC 14:12–19:16，也就是**晚了 7–12 小時**、台北 22:00 到隔天 03:00。
於是「當天就知道」變成「隔天凌晨才知道」—— 2026-11-24 部署連敗、網站晚三小時那次，
哨兵跑的時候早就修好了，一點痕跡都沒留下。

GitHub 排程的延遲沒有上限保證，這不是改 cron 修得好的。所以改由 Mac 的 launchd 在 15:20
用 workflow_dispatch 叫它（dispatch 觸發的執行幾秒內就開始），**GitHub 自己的排程留著當備援** ——
Mac 關機那天，排程雖然晚，至少還會跑。判定仍在 GitHub 上做、issue 仍由 workflow 開，
這支只負責「叫」，不判任何東西。

## 權杖

讀 `~/.config/github/sentinel-dispatch-token`（使用者自己建立的 fine-grained PAT，
只給目標 repo 的 **Actions: Read and write**，檔案權限 600）。
**這支不建立、不顯示、不印出權杖**；檔案不在就印一行說明、回退出碼 12。

## 退出碼
0 全部觸發成功　12 沒有權杖或設定壞了　14 網路或 API 失敗（看 log 裡的 HTTP 狀態）
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

OWNER = "GunDamnBoy"
WORKFLOW = "sentinel.yml"
TOKEN_FILE = os.path.expanduser("~/.config/github/sentinel-dispatch-token")


def main(argv) -> int:
    repos = argv[1:] or ["chart-of-the-day"]
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        print(f"{now} 找不到 {TOKEN_FILE} —— 哨兵只剩 GitHub 自己的排程（實際晚 7–12 小時）。"
              "建立方式見 kb-core/chart/CHANGELOG.md 2026-11-25。")
        return 12
    if not token:
        print(f"{now} {TOKEN_FILE} 是空的")
        return 12
    rc = 0
    for repo in repos:
        url = f"https://api.github.com/repos/{OWNER}/{repo}/actions/workflows/{WORKFLOW}/dispatches"
        req = urllib.request.Request(
            url, data=json.dumps({"ref": "main"}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"{now} {repo}：已觸發哨兵（HTTP {r.status}）")
        except urllib.error.HTTPError as e:
            # 401/403/404 多半是權杖權限或過期；**不印權杖、不印 header**
            print(f"{now} {repo}：觸發失敗 HTTP {e.code} {e.reason}")
            rc = 14
        except (urllib.error.URLError, OSError) as e:
            print(f"{now} {repo}：觸發失敗（網路）{e}")
            rc = 14
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
