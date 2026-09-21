from __future__ import annotations

import csv
import re
from pathlib import Path


class CsvReader:
    """Doc CSV voi fallback encoding, delimiter va header detection."""

    def __init__(self):
        self.encodings = [
            "utf-8-sig",
            "utf-8",
            "cp1252",
            "latin-1",
        ]

    @staticmethod
    def _tao_contract() -> dict:
        return {
            "status": "success",
            "file_type": "csv",
            "pdf_mode": None,
            "ocr_da_su_dung": False,
            "du_lieu": [],
            "canh_bao": [],
            "loi": None,
        }

    @staticmethod
    def _tao_header_duy_nhat(headers):
        ket_qua = []
        da_gap = {}

        for i, header in enumerate(headers, start=1):
            ten = str(header).strip()

            if not ten:
                ten = f"Column_{i}"

            if ten not in da_gap:
                da_gap[ten] = 0
                ket_qua.append(ten)
                continue

            da_gap[ten] += 1
            ten_moi = f"{ten}_{da_gap[ten]}"

            while ten_moi in da_gap:
                da_gap[ten] += 1
                ten_moi = f"{ten}_{da_gap[ten]}"

            da_gap[ten_moi] = 0
            ket_qua.append(ten_moi)

        return ket_qua

    @staticmethod
    def _dong_giong_du_lieu(row):
        """
        Kiem tra dong dau co ve la dong du lieu that hay khong.

        Vi du:
        NV001,...,an@example.com
        -> co kha nang cao la du lieu, khong phai header.
        """

        for cell in row:
            value = str(cell).strip()

            if not value:
                continue

            # Email
            if "@" in value:
                return True

            # Ma co chu + so, vi du NV001, EMP123
            if re.fullmatch(
                r"[A-Za-z_\-]{1,15}\d+",
                value,
            ):
                return True

            # So nguyen / so thuc
            if re.fullmatch(
                r"[-+]?\d+([.,]\d+)?",
                value,
            ):
                return True

        return False

    def _co_header(self, sample, rows):
        """
        Ket hop csv.Sniffer va heuristic bo sung.

        Sniffer co the doan sai khi tat ca cac cot deu la chuoi.
        """

        sniffer = csv.Sniffer()

        try:
            ket_qua_sniffer = sniffer.has_header(
                sample
            )
        except csv.Error:
            ket_qua_sniffer = None

        # Neu Sniffer chac chan co header
        if ket_qua_sniffer is True:
            return True

        # Neu dong dau giong du lieu that
        # thi coi la file khong header.
        if rows and self._dong_giong_du_lieu(
            rows[0]
        ):
            return False

        # Neu Sniffer khong chac chan / tra False,
        # nhung dong dau khong giong data,
        # uu tien coi dong dau la header.
        return True

    def read(
        self,
        file_path: str | Path,
    ) -> dict:

        path = Path(file_path)
        result = self._tao_contract()

        try:
            content = None
            used_encoding = None

            # =====================================================
            # ENCODING
            # =====================================================

            for encoding in self.encodings:
                try:
                    content = path.read_text(
                        encoding=encoding
                    )

                    used_encoding = encoding
                    break

                except UnicodeDecodeError:
                    continue

            if content is None:
                result["status"] = "error"
                result["loi"] = (
                    "CSV_ENCODING_ERROR"
                )
                return result

            if not content.strip():
                result["status"] = "error"
                result["loi"] = "EMPTY_FILE"
                return result

            if used_encoding not in (
                "utf-8-sig",
                "utf-8",
            ):
                result[
                    "canh_bao"
                ].append(
                    "CSV duoc doc bang "
                    "encoding fallback: "
                    f"{used_encoding}"
                )

            # =====================================================
            # DELIMITER
            # =====================================================

            sample = content[:8192]

            sniffer = csv.Sniffer()

            try:
                dialect = sniffer.sniff(
                    sample,
                    delimiters=[
                        ",",
                        ";",
                        "\t",
                    ],
                )

            except csv.Error:
                dialect = csv.excel

                result[
                    "canh_bao"
                ].append(
                    "Khong nhan dien duoc "
                    "delimiter, su dung dau phay."
                )

            # =====================================================
            # DOC ROW
            # =====================================================

            reader = csv.reader(
                content.splitlines(),
                dialect=dialect,
            )

            rows = []

            for row in reader:
                row = [
                    str(cell).strip()
                    for cell in row
                ]

                if any(
                    cell
                    for cell in row
                ):
                    rows.append(row)

            if not rows:
                result["status"] = "error"
                result["loi"] = "CSV_NO_DATA"
                return result

            so_cot = max(
                len(row)
                for row in rows
            )

            # =====================================================
            # HEADER DETECTION
            # =====================================================

            has_header = self._co_header(
                sample,
                rows,
            )

            if has_header:
                raw_headers = list(
                    rows[0]
                )

                raw_headers += [
                    ""
                ] * (
                    so_cot
                    - len(raw_headers)
                )

                headers = (
                    self._tao_header_duy_nhat(
                        raw_headers
                    )
                )

                data_source = rows[1:]

            else:
                headers = [
                    f"Column_{i}"
                    for i in range(
                        1,
                        so_cot + 1,
                    )
                ]

                # Rat quan trong:
                # khong bo dong du lieu dau.
                data_source = rows

                result[
                    "canh_bao"
                ].append(
                    "Khong phat hien header. "
                    "Da tao Column_1...Column_n "
                    "va giu nguyen dong du lieu "
                    "dau tien."
                )

            # =====================================================
            # DATA
            # =====================================================

            data_rows = []

            for index, row in enumerate(
                data_source,
                start=1,
            ):
                if len(row) != so_cot:
                    result[
                        "canh_bao"
                    ].append(
                        f"Dong {index} co "
                        f"{len(row)} cot, "
                        f"chuan hoa ve "
                        f"{so_cot} cot."
                    )

                row = (
                    row
                    + [""] * (
                        so_cot - len(row)
                    )
                )

                row = row[:so_cot]

                row_dict = dict(
                    zip(
                        headers,
                        row,
                    )
                )

                data_rows.append(
                    row_dict
                )

            result["du_lieu"].append(
                {
                    "sheet_name": None,
                    "headers": headers,
                    "rows": data_rows,
                }
            )

        except FileNotFoundError:
            result["status"] = "error"
            result["loi"] = "FILE_NOT_FOUND"

        except Exception as e:
            result["status"] = "error"
            result["loi"] = (
                f"CSV_READ_ERROR: {str(e)}"
            )

        return result