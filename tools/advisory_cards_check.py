#!/usr/bin/env python3
"""投顧知識庫｜寫卡輪的卡片自檢（2026-10-17 新增）。

採集員寫完 `cards_<代號>.json` 就跑這支；主線組稿前把七份一起丟進來再跑一次。
**每一個數字都從 `advisory/anchors.json` 讀**（窗口、長度、值域、豁免清單、各組下限），
這支只持有規則、不持有值 —— 同 SKILL 開頭那條「數字只有一個家」。

它與 `advisory_verify.py` 的分工：那支驗**組好的日期檔**（交稿前最後一關），
這支驗**還沒組起來的卡片陣列**（採集員交件當下），所以兩者會有幾條重疊（ts、去重、長度），
重疊是刻意的 —— 越早擋到，退件越便宜。

用法：
  python3 advisory_cards_check.py --repo <advisory-rewrite> --date 2026-10-17 cards_A.json [cards_B.json …]
退出碼：0 無錯誤（長度只算警告）；1 有錯誤；2 參數或檔案壞。
"""
import argparse, collections, datetime as dt, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHORS = os.path.join(os.path.dirname(HERE), "advisory", "anchors.json")
TPE = dt.timezone(dt.timedelta(hours=8))


def prev_urls(repo, date):
    days = sorted(f[:-5] for f in os.listdir(os.path.join(repo, "data"))
                  if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f) and f[:-5] < date)
    if not days:
        return None, set()
    d = json.load(open(os.path.join(repo, "data", days[-1] + ".json"), encoding="utf-8"))
    return days[-1], {c["url"] for s in d["sections"] for g in s["groups"] for c in g["cards"]}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--date", required=True, help="本期日期（台北）")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    try:
        anc = json.load(open(ANCHORS, encoding="utf-8"))
        cards = []
        for f in a.files:
            for c in json.load(open(f, encoding="utf-8")):
                c.setdefault("_file", os.path.basename(f)); cards.append(c)
    except Exception as e:
        print(f"讀檔失敗：{e}"); return 2
    day = dt.date.fromisoformat(a.date)
    w = anc["window"]
    start = dt.datetime.combine(day + dt.timedelta(days=w["from_day_offset"]), dt.time(w["from_hour_taipei"]), TPE)
    mode = "weekend" if start.weekday() >= 5 else "weekday"
    now = dt.datetime.now(TPE)
    groups = {g["name"]: g for g in anc["groups"]}
    vocab = anc["card_vocab"]; L = anc["lengths"]; exempt = set(anc["dedup_exempt"])
    pday, prev = prev_urls(a.repo, a.date)
    errs, warns = [], []
    cnt, urls = collections.Counter(), collections.Counter()
    for i, c in enumerate(cards):
        tag = f"{c.get('_file')}#{i} {str(c.get('title',''))[:24]}"
        for k in ("group", "src", "tag", "tagcls", "date", "ts", "title", "deep", "body", "bullets", "url", "tone"):
            if k not in c: errs.append(f"{tag}: 缺欄位 {k}")
        if c.get("group") not in groups: errs.append(f"{tag}: group 不在 anchors.groups：{c.get('group')}")
        if c.get("tone") not in vocab["tone"]: errs.append(f"{tag}: tone 不在值域（不要寫複合值）：{c.get('tone')}")
        if c.get("tagcls") not in vocab["tagcls"]: errs.append(f"{tag}: tagcls 不在值域：{c.get('tagcls')}")
        if not isinstance(c.get("body"), str): errs.append(f"{tag}: body 必須是字串")
        try:
            ts = dt.datetime.fromisoformat(c["ts"])
            if ts.tzinfo is None: errs.append(f"{tag}: ts 沒有時區")
            elif ts < start: errs.append(f"{tag}: ts 早於窗口起點 {start.isoformat()}")
            elif ts > now: errs.append(f"{tag}: ts 在未來")
            elif c.get("date") != ts.astimezone(TPE).date().isoformat():
                errs.append(f"{tag}: date 不等於 ts 的台北日期")
        except Exception as e:
            errs.append(f"{tag}: ts 壞掉（{e}）")
        u = c.get("url")
        if u in prev and u not in exempt: errs.append(f"{tag}: url 與前一版 {pday} 重複")
        urls[u] += 1
        n = len(c.get("body") or "") + sum(len(b) for b in c.get("bullets") or [])
        lo, hi = L["deep_card"] if c.get("deep") else L["regular_card"]
        if not lo <= n <= hi: warns.append(f"{tag}: 長度 {n} 不在 {lo}–{hi}")
        cnt[c.get("group")] += 1
    for u, n in urls.items():
        if n > 1: errs.append(f"同版重複 url（{n} 張）：{u}")
    print(f"窗口起點 {start.isoformat()}（{mode}）；前一版 {pday}；共 {len(cards)} 張")
    print("各組張數（／下限）：" + "、".join(f"{g} {cnt[g]}/{groups[g]['floor'][mode]}" for g in groups if cnt[g]))
    print(f"deep {sum(1 for c in cards if c.get('deep'))}（全站區間 {L['deep_card_count']}）；"
          f"thread {sum(1 for c in cards if c.get('thread'))}（全站區間 {L['threaded_cards_per_day']}）")
    for x in warns: print("警告：" + x)
    for x in errs: print("錯誤：" + x)
    print("OK 無錯誤" if not errs else f"{len(errs)} 個錯誤")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
