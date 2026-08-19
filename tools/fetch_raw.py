#!/usr/bin/env python3
"""管線 A 的進入點：取一批序列，寫成資料 repo 的 raw/YYYY-MM-DD.json。

用法：
  fetch_raw.py <raw 目錄> <ident> [<ident> ...]

例：
  fetch_raw.py raw FRED:DGS10

退出碼（見 kbcore/result.py）：
  0 成功 · 3 代號無法路由／解析失敗 · 5 憑證失效或上游不通

**憑證失效與取不到資料是分開的兩件事。** 舊系統的 403 在「權限不足」與
「憑證已撤銷」時症狀完全相同，所以這裡把 AUTH_FAILED 單獨具名。
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.fetch import (AuthFailed, FetchError, ParseFailed,  # noqa: E402
                          UnknownIdent, UpstreamError, get)
from kbcore.result import Exit  # noqa: E402


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return Exit.BAD_INPUT

    outdir = Path(argv[1])
    idents = argv[2:]
    today = dt.date.today().isoformat()

    series, failed = {}, []
    for ident in idents:
        try:
            series[ident] = get(ident)
            n = len(series[ident]["points"])
            last = series[ident]["points"][-1]
            print(f"ok       {ident:<16} {n} 點，末日 {last[0]} = {last[1]}")
        except AuthFailed as e:
            print(f"AUTH_FAILED  {ident:<16} {e}", file=sys.stderr)
            return Exit.ENVIRONMENT
        except (UnknownIdent, ParseFailed) as e:
            print(f"BAD_INPUT    {ident:<16} {e}", file=sys.stderr)
            return Exit.BAD_INPUT
        except UpstreamError as e:
            print(f"UPSTREAM     {ident:<16} {e}", file=sys.stderr)
            failed.append({"ident": ident, "reason": str(e)})

    if not series:
        print("一條序列都沒取到", file=sys.stderr)
        return Exit.ENVIRONMENT

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{today}.json"
    payload = {
        "date": today,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "series": series,
        "failed": failed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"\n寫入 {path}（{len(series)} 條成功、{len(failed)} 條失敗）")
    return Exit.OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
