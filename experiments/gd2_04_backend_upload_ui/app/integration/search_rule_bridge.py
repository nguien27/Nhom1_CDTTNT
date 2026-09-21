from __future__ import annotations
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

from ..database import ConnectionRepositoryAdapter

MATCH_ORDER = {"EXACT": 4, "TOKEN": 3, "PARTIAL": 2, "FUZZY": 1}


def _find_gd2_03() -> Path:
    here = Path(__file__).resolve()
    experiments = here.parents[3]
    p = experiments / "gd2_03_search_rule_engine"
    if (p / "src" / "search_engine.py").exists() and (p / "src" / "rule_engine.py").exists():
        return p
    raise RuntimeError("Không tìm thấy experiments/gd2_03_search_rule_engine.")


def _load_classes():
    root = _find_gd2_03()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    SearchEngine = importlib.import_module("src.search_engine").SearchEngine
    RuleEngine = importlib.import_module("src.rule_engine").RuleEngine
    return SearchEngine, RuleEngine


class SearchRuleBridge:
    """Adapter API. Search/Rule logic vẫn nằm hoàn toàn trong GĐ2-03."""
    def __init__(self, conn):
        SearchEngine, RuleEngine = _load_classes()
        self.conn = conn
        repo = ConnectionRepositoryAdapter(conn)
        self.search_engine = SearchEngine(repo)
        self.rule_engine = RuleEngine(repo)

    @staticmethod
    def _normalize_employee_item(item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item)
        out["loai_doi_tuong"] = "NHAN_VIEN"
        if out.get("ma_nhan_vien"):
            out["id_doi_tuong"] = out["ma_nhan_vien"]
        return out

    @staticmethod
    def _normalize_unit_item(item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item)
        out["loai_doi_tuong"] = "DON_VI"
        if out.get("ma_don_vi"):
            out["id_doi_tuong"] = out["ma_don_vi"]
        return out

    def search(self, query: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        # Gọi trực tiếp 2 entrypoint GĐ2-03 rồi chỉ hợp nhất response.
        window = max(limit, offset + limit)
        e = self.search_engine.search_nhan_vien(query, limit=window, offset=0)
        u = self.search_engine.search_don_vi(query, limit=window, offset=0)
        employees = [self._normalize_employee_item(x) for x in e.get("ket_qua", e.get("data", []))]
        units = [self._normalize_unit_item(x) for x in u.get("ket_qua", u.get("data", []))]
        items: List[Dict[str, Any]] = employees + units
        items.sort(key=lambda x: (-MATCH_ORDER.get(x.get("loai_khop"), 0), -float(x.get("do_khop") or 0), str(x.get("ho_ten") or x.get("ten_don_vi") or "")))
        total = int(e.get("tong_ket_qua", len(employees))) + int(u.get("tong_ket_qua", len(units)))
        return {
            "query": query,
            "tong_ket_qua": total,
            "limit": limit,
            "offset": offset,
            "ket_qua": items[offset:offset + limit],
        }

    def employee_status(self, ma_nhan_vien: str) -> Dict[str, Any]:
        result = self.rule_engine.evaluate_employee_salary_rule(ma_nhan_vien)
        return self._status_contract(result)

    def unit_status(self, ma_don_vi: str) -> Dict[str, Any]:
        result = self.rule_engine.evaluate_unit_salary_rule(ma_don_vi)
        return self._status_contract(result)

    def _status_contract(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        result = raw.get("ket_qua") or raw.get("result") or "CHUA_XAC_DINH"
        evidence = raw.get("can_cu") or raw.get("evidence")
        source = raw.get("nguon_quy_tac")
        rule_id = raw.get("ma_quy_tac") or raw.get("applied_rule")
        text = (evidence or "").strip().lower()
        la_mock = source == "MOCK" or text.startswith("[mock]") or text.startswith("mock")
        if rule_id:
            row = self.conn.execute("SELECT la_mock FROM business_rule WHERE ma_quy_tac=?", (rule_id,)).fetchone()
            if row is not None:
                la_mock = bool(row[0])
        source_norm = source
        if source in {"quy_tac_tra_luong", "BUSINESS_RULE", "MOCK"}:
            source_norm = "BUSINESS_RULE"
        elif source and str(source).lower() in {"ngoai_le_ca_nhan", "ngoai_le"}:
            source_norm = "NGOAI_LE_CA_NHAN"
        return {
            "ket_qua": result,
            "can_cu": evidence,
            "ma_quy_tac": rule_id,
            "nguon_quy_tac": source_norm,
            "la_mock": bool(la_mock),
            "ghi_chu": raw.get("ghi_chu") or "",
        }
