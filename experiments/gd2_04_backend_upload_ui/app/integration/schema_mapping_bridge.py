from __future__ import annotations
import importlib
import importlib.util
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Các field tích hợp ngoài contract AI 5 lớp của GĐ2-02.
# Chỉ exact alias, không fuzzy/AI và không quyết định nghiệp vụ.
INTEGRATION_EXACT_ALIASES = {
    "ma don vi": "MA_DON_VI_NGUON",
    "ma don vi nguon": "MA_DON_VI_NGUON",
    "don vi cha": "DON_VI_CHA",
    "chuc vu": "CHUC_VU", "vi tri": "CHUC_VU", "position": "CHUC_VU",
    "email": "EMAIL", "thu dien tu": "EMAIL",
    "ket qua": "KET_QUA", "ket qua tra luong": "KET_QUA", "trang thai tra luong": "KET_QUA",
    "can cu": "CAN_CU", "can cu phap ly": "CAN_CU", "can cu chi tra": "CAN_CU",
    "ma quy tac": "MA_QUY_TAC", "rule code": "MA_QUY_TAC",
    "ten quy tac": "TEN_QUY_TAC",
    "muc uu tien": "MUC_UU_TIEN", "priority": "MUC_UU_TIEN",
    "ngay hieu luc": "NGAY_HIEU_LUC", "ngay het hieu luc": "NGAY_HET_HIEU_LUC",
    "dang ap dung": "DANG_AP_DUNG", "la mock": "LA_MOCK", "ghi chu": "GHI_CHU",
}


def _norm(text: str) -> str:
    value = str(text or "").strip().lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(value.replace("_", " ").replace("-", " ").split())


def _find_gd2_02() -> Path:
    here = Path(__file__).resolve()
    experiments = here.parents[3]
    p = experiments / "gd2_02_ai_schema_mapping"
    if (p / "src" / "predict.py").exists():
        return p
    raise RuntimeError("Không tìm thấy experiments/gd2_02_ai_schema_mapping.")


def _load_predictor():
    root = _find_gd2_02()
    src_dir = root / "src"
    package_name = "gd2_02_src"
    if package_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package_name, src_dir / "__init__.py", submodule_search_locations=[str(src_dir)]
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Không thể nạp package GĐ2-02.")
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = pkg
        spec.loader.exec_module(pkg)
    module = importlib.import_module(f"{package_name}.predict")
    return module.SchemaMappingPredictor()


class SchemaMappingBridge:
    def __init__(self):
        self.predictor = _load_predictor()

    def predict_column(self, header: str) -> Dict[str, Any]:
        norm = _norm(header)
        if norm in INTEGRATION_EXACT_ALIASES:
            return {
                "original_text": header,
                "label": INTEGRATION_EXACT_ALIASES[norm],
                "confidence": 1.0,
                "accepted": True,
                "source": "gd2_04_exact_contract_alias",
            }

        if hasattr(self.predictor, "du_doan_truong"):
            result = self.predictor.du_doan_truong(header)
        elif hasattr(self.predictor, "predict_single"):
            result = self.predictor.predict_single(header)
        else:
            raise RuntimeError("GĐ2-02 predictor không có API dự đoán tương thích.")
        result = dict(result)
        result.setdefault("original_text", header)
        result["source_module"] = "GD2-02"
        return result

    def detect_mapping(self, headers: List[str]) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        mapping: Dict[str, str] = {}
        details: List[Dict[str, Any]] = []
        for header in headers:
            info = self.predict_column(header)
            details.append(info)
            label = info.get("label")
            if info.get("accepted") and label and label != "OTHER" and label not in mapping:
                mapping[label] = header
        return mapping, details
