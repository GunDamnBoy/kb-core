# kb-core

六套知識庫系統的共用底盤。**必須維持 Public** —— 資料 repo 的 GitHub Actions
要能免認證 checkout 本 repo，這是「零 PAT」架構成立的前提。

本 repo 不含任何秘密：Gemini key 在 Mac 的 `~/.podfetch/`，Tiingo／FRED 在
GitHub Actions secret，推送用 SSH key。

- `kbcore/` — 底盤模組（結果與退出碼、檢查物件、報告）
- `checks/` — 檢查定義，每條必須有 `covers`、`blind_to`、`fixture`
- `tools/verify.py` — 檢查器進入點（`--selftest` / `--write-lock` / `<payload>`）
- `checks.lock` — 已知 check id 集合，**只增不減**
