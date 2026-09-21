"""Bridge mỏng tới Search Engine + Rule Engine canonical của GĐ2-03.

GĐ3-04 tuyệt đối không sao chép logic tìm kiếm, ranking hay quyết định
YES/NO/CHUA_XAC_DINH. Module này chỉ resolve import và cấp adapter repository
đúng interface mà GĐ2-03 yêu cầu.
"""

from __future__ import annotations

import sys
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[4]
GD2_03_DIR = PROJECT_ROOT / "experiments" / "gd2_03_search_rule_engine"

if not GD2_03_DIR.exists():
    raise RuntimeError(
        "Không tìm thấy experiments/gd2_03_search_rule_engine canonical. "
        "GĐ3-04 không được fallback sang gd1_04_search_rule_engine."
    )

if str(GD2_03_DIR) not in sys.path:
    sys.path.insert(0, str(GD2_03_DIR))

from src.normalization import normalize_vietnamese  # noqa: E402
from src.rule_engine import RuleEngine  # noqa: E402
from src.search_engine import SearchEngine  # noqa: E402


class ConnectionRepositoryAdapter:
    """Adapter DB tối thiểu cho interface `repo.execute_query` của GĐ2-03.

    Đây chỉ là adapter hạ tầng; không chứa search/rule/business logic.
    """

    def __init__(self, connection, lock: RLock | None = None):
        self.connection = connection
        self.lock = lock or RLock()

    def get_connection(self):
        return self.connection

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self.lock:
            cursor = self.connection.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


__all__ = [
    "ConnectionRepositoryAdapter",
    "SearchEngine",
    "RuleEngine",
    "normalize_vietnamese",
]
