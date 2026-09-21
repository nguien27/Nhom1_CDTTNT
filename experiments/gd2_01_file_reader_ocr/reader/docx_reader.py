from __future__ import annotations

from pathlib import Path

import docx

from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


class DocxReader:
    """Doc paragraph va table trong DOCX."""

    @staticmethod
    def _tao_contract() -> dict:
        return {
            "status": "success",
            "file_type": "docx",
            "pdf_mode": None,
            "ocr_da_su_dung": False,
            "du_lieu": [],
            "canh_bao": [],
            "loi": None,
        }

    @staticmethod
    def _duyet_block(document):
        """Duyet paragraph va table theo dung thu tu."""

        body = document.element.body

        for child in body.iterchildren():

            if isinstance(child, CT_P):
                yield (
                    "paragraph",
                    Paragraph(
                        child,
                        document,
                    ),
                )

            elif isinstance(child, CT_Tbl):
                yield (
                    "table",
                    Table(
                        child,
                        document,
                    ),
                )

    @staticmethod
    def _tao_header_duy_nhat(cells):
        headers = []
        da_gap = {}

        for i, cell in enumerate(
            cells,
            start=1,
        ):
            ten = (
                cell.text
                .strip()
                .replace("\n", " ")
            )

            if not ten:
                ten = f"Column_{i}"

            if ten not in da_gap:
                da_gap[ten] = 0
                headers.append(ten)
                continue

            da_gap[ten] += 1

            ten_moi = (
                f"{ten}_{da_gap[ten]}"
            )

            while ten_moi in da_gap:
                da_gap[ten] += 1

                ten_moi = (
                    f"{ten}_{da_gap[ten]}"
                )

            da_gap[ten_moi] = 0
            headers.append(ten_moi)

        return headers

    def read(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        result = self._tao_contract()

        try:
            document = docx.Document(path)

            table_index = 0
            paragraph_index = 0

            for loai, block in self._duyet_block(
                document
            ):
                if loai == "paragraph":
                    text = block.text.strip()

                    if not text:
                        continue

                    paragraph_index += 1

                    result["du_lieu"].append(
                        {
                            "sheet_name": (
                                f"Paragraph_"
                                f"{paragraph_index}"
                            ),
                            "headers": [
                                "noi_dung"
                            ],
                            "rows": [
                                {
                                    "noi_dung": text
                                }
                            ],
                        }
                    )

                elif loai == "table":
                    table_index += 1

                    if not block.rows:
                        result[
                            "canh_bao"
                        ].append(
                            f"Table_{table_index} rong."
                        )
                        continue

                    headers = (
                        self._tao_header_duy_nhat(
                            block.rows[0].cells
                        )
                    )

                    data_rows = []

                    for row in block.rows[1:]:
                        row_dict = {}
                        co_du_lieu = False

                        cells = row.cells

                        for i, header in enumerate(
                            headers
                        ):
                            value = ""

                            if i < len(cells):
                                value = (
                                    cells[i]
                                    .text
                                    .strip()
                                    .replace(
                                        "\n",
                                        " ",
                                    )
                                )

                            if value:
                                co_du_lieu = True

                            row_dict[
                                header
                            ] = value

                        if co_du_lieu:
                            data_rows.append(
                                row_dict
                            )

                    result["du_lieu"].append(
                        {
                            "sheet_name": (
                                f"Table_"
                                f"{table_index}"
                            ),
                            "headers": headers,
                            "rows": data_rows,
                        }
                    )

            if not result["du_lieu"]:
                result["status"] = "error"
                result["loi"] = "DOCX_NO_DATA"

        except FileNotFoundError:
            result["status"] = "error"
            result["loi"] = "FILE_NOT_FOUND"

        except Exception as e:
            result["status"] = "error"
            result["loi"] = (
                f"DOCX_READ_ERROR: {str(e)}"
            )

        return result