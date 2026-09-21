"""Bridge tới GĐ3-03, từ đó sử dụng GĐ3-01 và GĐ3-02 canonical.

Luồng input bắt buộc:
GĐ3-04 -> GĐ3-03 -> GĐ3-01 + GĐ3-02.

Nhờ vậy backend không tự viết lại File Reader/OCR, Information Extraction,
Schema Mapping, confidence, validation UI hay commit dữ liệu nhân viên ổn định.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
GD3_03_DIR = PROJECT_ROOT / "experiments" / "gd3_03_input_mapping_ui"

if not GD3_03_DIR.exists():
    raise RuntimeError(
        "Không tìm thấy experiments/gd3_03_input_mapping_ui. "
        "Hãy lấy bản GĐ3-03 mới nhất từ Leader trước khi chạy GĐ3-04."
    )

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.gd3_03_input_mapping_ui.app.adapter import (  # noqa: E402
    InputAnalysisError,
    analyze_input,
)
from experiments.gd3_03_input_mapping_ui.app.commit_service import CommitService  # noqa: E402
from experiments.gd3_03_input_mapping_ui.app.mapping_service import (  # noqa: E402
    SCHEMA_FIELDS,
    MappingService,
)
from experiments.gd3_03_input_mapping_ui.app.validation_service import ValidationService  # noqa: E402

__all__ = [
    "InputAnalysisError",
    "analyze_input",
    "CommitService",
    "MappingService",
    "ValidationService",
    "SCHEMA_FIELDS",
]
