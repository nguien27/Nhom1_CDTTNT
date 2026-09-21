from __future__ import annotations

import io
import time


class OcrEngine:
    """Wrapper PaddleOCR ho tro API 2.x va 3.x."""

    def __init__(self):
        self.ocr_instance = None
        self.init_error = None

        self._khoi_tao()

    @property
    def available(self) -> bool:
        return (
            self.ocr_instance
            is not None
        )

    def _khoi_tao(self):
        try:
            from paddleocr import PaddleOCR

            try:
                # PaddleOCR 3.x
                self.ocr_instance = PaddleOCR(
                    lang="vi",
                    device="cpu",
                    enable_mkldnn=False,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )

            except TypeError:
                try:
                    # PaddleOCR 2.x
                    self.ocr_instance = PaddleOCR(
                        lang="vi",
                        use_angle_cls=True,
                        enable_mkldnn=False,
                    )

                except TypeError:
                    self.ocr_instance = PaddleOCR(
                        lang="vi"
                    )

        except Exception as e:
            self.ocr_instance = None
            self.init_error = str(e)

    @staticmethod
    def _tien_xu_ly(
        image,
        grayscale=True,
        contrast=1.5,
        sharpen=False,
    ):
        from PIL import (
            ImageEnhance,
            ImageFilter,
        )

        if grayscale:
            image = image.convert("L")

        if (
            contrast is not None
            and float(contrast) != 1.0
        ):
            image = (
                ImageEnhance
                .Contrast(image)
                .enhance(float(contrast))
            )

        if sharpen:
            image = image.filter(
                ImageFilter.SHARPEN
            )

        return image

    def ocr_page(
        self,
        mupdf_page,
        dpi=200,
        grayscale=True,
        contrast=1.5,
        sharpen=False,
    ):
        from PIL import Image

        start = time.perf_counter()

        result = {
            "text": "",
            "lines": [],
            "time_s": 0.0,
            "success": False,
            "loi": None,
        }

        if not self.available:
            result["loi"] = (
                self.init_error
                or "PADDLEOCR_NOT_AVAILABLE"
            )
            return result

        try:
            pix = mupdf_page.get_pixmap(
                dpi=dpi
            )

            image = Image.open(
                io.BytesIO(
                    pix.tobytes("png")
                )
            )

            image = self._tien_xu_ly(
                image,
                grayscale=grayscale,
                contrast=contrast,
                sharpen=sharpen,
            )

            result = self.ocr_image(
                image
            )

            result["time_s"] = round(
                time.perf_counter()
                - start,
                3,
            )

            return result

        except Exception as e:
            result["time_s"] = round(
                time.perf_counter()
                - start,
                3,
            )

            result["loi"] = (
                f"OCR_PAGE_ERROR: {str(e)}"
            )

            return result

    def ocr_image(self, image):
        import numpy as np

        start = time.perf_counter()

        result = {
            "text": "",
            "lines": [],
            "time_s": 0.0,
            "success": False,
            "loi": None,
        }

        if not self.available:
            result["loi"] = (
                self.init_error
                or "PADDLEOCR_NOT_AVAILABLE"
            )
            return result

        try:
            image_rgb = np.array(
                image.convert("RGB")
            )

            lines = []

            # PaddleOCR 3.x
            if hasattr(
                self.ocr_instance,
                "predict",
            ):
                raw_result = (
                    self.ocr_instance
                    .predict(image_rgb)
                )

                if raw_result is not None:
                    self._extract_texts(
                        raw_result,
                        lines,
                    )

            # PaddleOCR 2.x
            elif hasattr(
                self.ocr_instance,
                "ocr",
            ):
                raw_result = (
                    self.ocr_instance
                    .ocr(
                        image_rgb,
                        cls=True,
                    )
                )

                if (
                    raw_result
                    and raw_result[0]
                    is not None
                ):
                    for line in raw_result[0]:

                        if (
                            isinstance(
                                line,
                                list,
                            )
                            and len(line) == 2
                        ):
                            _, data = line

                            text = data[0]

                            if (
                                isinstance(
                                    text,
                                    str,
                                )
                                and text.strip()
                            ):
                                lines.append(
                                    text.strip()
                                )

            else:
                result["loi"] = (
                    "PADDLEOCR_API_NOT_SUPPORTED"
                )

                return result

            # Khong deduplicate.
            # Hai dong trung nhau van co the
            # la hai dong du lieu that.
            result["lines"] = lines

            result["text"] = "\n".join(
                lines
            )

            result["success"] = True

            result["time_s"] = round(
                time.perf_counter()
                - start,
                3,
            )

            return result

        except Exception as e:
            result["time_s"] = round(
                time.perf_counter()
                - start,
                3,
            )

            result["loi"] = (
                f"OCR_IMAGE_ERROR: {str(e)}"
            )

            return result

    @staticmethod
    def _extract_texts(
        obj,
        result_list,
    ):
        if obj is None:
            return

        if isinstance(obj, dict):

            rec_texts = obj.get(
                "rec_texts"
            )

            if isinstance(
                rec_texts,
                list,
            ):
                for text in rec_texts:

                    if (
                        isinstance(
                            text,
                            str,
                        )
                        and text.strip()
                    ):
                        result_list.append(
                            text.strip()
                        )

            # Khong duyet lai rec_texts
            # de tranh trung text.
            for key, value in obj.items():

                if key == "rec_texts":
                    continue

                OcrEngine._extract_texts(
                    value,
                    result_list,
                )

            return

        if isinstance(
            obj,
            (list, tuple),
        ):
            # Format API OCR cu:
            # [box, (text, confidence)]
            if (
                len(obj) >= 2
                and isinstance(
                    obj[1],
                    (list, tuple),
                )
                and len(obj[1]) >= 1
                and isinstance(
                    obj[1][0],
                    str,
                )
            ):
                text = (
                    obj[1][0]
                    .strip()
                )

                if text:
                    result_list.append(
                        text
                    )

                return

            for item in obj:
                OcrEngine._extract_texts(
                    item,
                    result_list,
                )

            return

        for attr in (
            "json",
            "res",
        ):
            if hasattr(obj, attr):

                try:
                    value = getattr(
                        obj,
                        attr,
                    )

                    OcrEngine._extract_texts(
                        value,
                        result_list,
                    )

                except Exception:
                    pass