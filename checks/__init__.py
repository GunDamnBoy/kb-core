"""匯入即註冊。

每個 suite 一個模組，但**全部在這裡一次匯入**——因為 `checks.lock` 與自檢是
全域的。少匯入一個模組，那個 suite 的檢查會從 lock 比對裡整組消失，而 lock
只會說「有 id 不見了」，不會說「你忘了 import」。
"""
from . import advisory  # noqa: F401  suite=advisory
from . import podcast   # noqa: F401  suite=podcast
from . import chart     # noqa: F401  suite=chart
from . import demo      # noqa: F401  suite=draft
from . import sentinel  # noqa: F401  suite=sentinel
from . import repo      # noqa: F401  suite=repo
from . import watch     # noqa: F401  suite=watch
