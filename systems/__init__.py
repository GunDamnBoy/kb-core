"""匯入即登記。每個系統一個模組。

新增一套系統要做三件事，缺一它就不會被 publish 認出來：
建一個模組、在這裡匯入、把 `.kb-data-repo` 寫成同一個 id。
"""
from . import advisory  # noqa: F401
from . import podcast   # noqa: F401
from . import chart     # noqa: F401
from . import tracer    # noqa: F401
from . import research  # noqa: F401
