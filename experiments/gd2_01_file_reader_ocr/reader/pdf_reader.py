from __future__ import annotations

from pathlib import Path

import pymupdf
import pdfplumber

from .ocr_engine import OcrEngine


class PdfReader:
    """Doc PDF text, scan va mixed."""

    # Nguong chi ap dung khi trang
    # vua co image vua co text layer.
    NGUONG_TEXT_SCAN = 50

    OCR_DPI = 200
    OCR_GRAYSCALE = True
    OCR_CONTRAST = 1.5

    def __init__(self):
        self.ocr_engine = OcrEngine()

    @staticmethod
    def _tao_contract() -> dict:
        return {
            "status": "success",
            "file_type": "pdf",
            "pdf_mode": None,
            "ocr_da_su_dung": False,
            "du_lieu": [],
            "canh_bao": [],
            "loi": None,
        }

    def _phan_loai_trang(
        self,
        page,
    ) -> str:
        text = page.get_text() or ""

        char_count = len(
            text.strip()
        )

        has_images = bool(
            page.get_images()
        )

        # Khong text, khong image
        if (
            char_count == 0
            and not has_images
        ):
            return "empty"

        # Co text va khong image:
        # day la PDF text du text ngan.
        if (
            char_count > 0
            and not has_images
        ):
            return "text"

        # Trang co image va co text layer
        # du lon thi uu tien text layer.
        if (
            char_count
            >= self.NGUONG_TEXT_SCAN
        ):
            return "text"

        # Co image, text layer qua it
        # hoac khong co text.
        return "scan"

    def read(
        self,
        file_path: str | Path,
    ) -> dict:
        path = Path(file_path)
        result = self._tao_contract()

        try:
            with pymupdf.open(path) as doc:

                if getattr(
                    doc,
                    "needs_pass",
                    False,
                ):
                    result["status"] = "error"
                    result["loi"] = "PDF_ENCRYPTED"

                    return result

                if len(doc) == 0:
                    result["status"] = "error"
                    result["loi"] = "PDF_NO_PAGES"

                    return result

                with pdfplumber.open(
                    path
                ) as plumber_doc:

                    page_types = []

                    for page_num in range(
                        len(doc)
                    ):
                        page = doc[
                            page_num
                        ]

                        page_type = (
                            self._phan_loai_trang(
                                page
                            )
                        )

                        page_types.append(
                            page_type
                        )

                        if page_type == "empty":

                            result[
                                "canh_bao"
                            ].append(
                                f"Trang "
                                f"{page_num + 1} "
                                f"rong."
                            )

                        elif page_type == "text":

                            self._xu_ly_text(
                                plumber_doc,
                                page_num,
                                result,
                            )

                        elif page_type == "scan":

                            self._xu_ly_scan(
                                page,
                                page_num,
                                result,
                            )

                has_text = (
                    "text"
                    in page_types
                )

                has_scan = (
                    "scan"
                    in page_types
                )

                if (
                    has_text
                    and has_scan
                ):
                    result[
                        "pdf_mode"
                    ] = "mixed"

                elif has_text:
                    result[
                        "pdf_mode"
                    ] = "text"

                elif has_scan:
                    result[
                        "pdf_mode"
                    ] = "scan"

                else:
                    result[
                        "pdf_mode"
                    ] = None

                # Khong doc duoc bat ky du lieu nao
                if not result["du_lieu"]:

                    if (
                        has_scan
                        and not result[
                            "ocr_da_su_dung"
                        ]
                    ):
                        result[
                            "status"
                        ] = "error"

                        result[
                            "loi"
                        ] = (
                            "OCR_UNAVAILABLE_OR_FAILED"
                        )

                    elif has_scan:
                        result[
                            "status"
                        ] = "error"

                        result[
                            "loi"
                        ] = "OCR_NO_TEXT"

                    else:
                        result[
                            "status"
                        ] = "error"

                        result[
                            "loi"
                        ] = (
                            "PDF_NO_READABLE_CONTENT"
                        )

        except FileNotFoundError:
            result["status"] = "error"
            result["loi"] = "FILE_NOT_FOUND"

        except Exception as e:
            result["status"] = "error"

            result["loi"] = (
                f"PDF_READ_ERROR: {str(e)}"
            )

        return result

    @staticmethod
    def _tao_header_duy_nhat(
        raw_headers,
    ):
        headers = []
        da_gap = {}

        for i, value in enumerate(
            raw_headers,
            start=1,
        ):
            if (
                value is not None
                and str(value).strip()
            ):
                ten = (
                    str(value)
                    .replace(
                        "\n",
                        " ",
                    )
                    .strip()
                )

            else:
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

    def _xu_ly_text(
        self,
        plumber_doc,
        page_num,
        result,
    ):
        page = plumber_doc.pages[
            page_num
        ]

        tables = (
            page.extract_tables()
            or []
        )

        co_bang = False

        # Neu PDF co bang thi uu tien bang,
        # tranh dua ca raw text va table
        # dan den duplicate data.
        for table_index, table in enumerate(
            tables,
            start=1,
        ):
            if not table:
                continue

            clean_table = []

            for row in table:

                if not row:
                    continue

                if any(
                    cell is not None
                    and str(cell).strip()
                    for cell in row
                ):
                    clean_table.append(
                        row
                    )

            if not clean_table:
                continue

            co_bang = True

            so_cot = max(
                len(row)
                for row in clean_table
            )

            raw_headers = list(
                clean_table[0]
            )

            raw_headers += [
                None
            ] * (
                so_cot
                - len(raw_headers)
            )

            headers = (
                self._tao_header_duy_nhat(
                    raw_headers
                )
            )

            data_rows = []

            for row in clean_table[1:]:

                row = list(row)

                row += [
                    None
                ] * (
                    so_cot - len(row)
                )

                row_dict = {}
                co_du_lieu = False

                for i, header in enumerate(
                    headers
                ):
                    value = row[i]

                    if value is None:
                        value = ""

                    else:
                        value = (
                            str(value)
                            .replace(
                                "\n",
                                " ",
                            )
                            .strip()
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
                        f"Page_"
                        f"{page_num + 1}"
                        f"_Table_"
                        f"{table_index}"
                    ),
                    "headers": headers,
                    "rows": data_rows,
                }
            )

        # Chi lay raw text khi trang
        # khong trich xuat duoc bang.
        if not co_bang:

            text = page.extract_text()

            if not text:
                return

            rows = []

            for line in text.splitlines():

                line = line.strip()

                if line:
                    rows.append(
                        {
                            "noi_dung": line
                        }
                    )

            if rows:
                result[
                    "du_lieu"
                ].append(
                    {
                        "sheet_name": (
                            f"Page_"
                            f"{page_num + 1}"
                            f"_Text"
                        ),
                        "headers": [
                            "noi_dung"
                        ],
                        "rows": rows,
                    }
                )

    def _xu_ly_scan(
        self,
        page,
        page_num,
        result,
    ):
        ocr_result = (
            self.ocr_engine
            .ocr_page(
                page,
                dpi=self.OCR_DPI,
                grayscale=(
                    self.OCR_GRAYSCALE
                ),
                contrast=(
                    self.OCR_CONTRAST
                ),
            )
        )

        # Chi True khi OCR da chay
        # va PaddleOCR tra ket qua thanh cong.
        if ocr_result.get(
            "success"
        ):
            result[
                "ocr_da_su_dung"
            ] = True

            lines = []

            for line in ocr_result.get(
                "lines",
                [],
            ):
                if (
                    isinstance(
                        line,
                        str,
                    )
                    and line.strip()
                ):
                    lines.append(
                        line.strip()
                    )

            if lines:
                result[
                    "du_lieu"
                ].append(
                    {
                        "sheet_name": (
                            f"Page_"
                            f"{page_num + 1}"
                            f"_OCR"
                        ),
                        "headers": [
                            "noi_dung"
                        ],
                        "rows": [
                            {
                                "noi_dung":
                                line
                            }
                            for line in lines
                        ],
                    }
                )

            else:
                result[
                    "canh_bao"
                ].append(
                    f"OCR da chay o trang "
                    f"{page_num + 1} "
                    f"nhung khong nhan "
                    f"duoc text."
                )

        else:
            loi = (
                ocr_result.get(
                    "loi"
                )
                or "khong ro nguyen nhan"
            )

            result[
                "canh_bao"
            ].append(
                f"OCR that bai o trang "
                f"{page_num + 1}: {loi}"
            )