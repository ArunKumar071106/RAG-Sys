"""OCR engines for posters, notices, banners and scanned documents.

``rapidocr`` (ONNX, models bundled in the wheel - works offline) is the
default. ``tesseract`` is supported when the binary and ``pytesseract``
are installed. ``none`` disables OCR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str
    confidence: float


class OcrEngine(Protocol):
    name: str

    def read(self, path: Path) -> OcrResult: ...


class NoOcr:
    name = "none"

    def read(self, path: Path) -> OcrResult:
        return OcrResult("", 0.0)


def _join_lines(boxes: list[tuple[list, str, float]]) -> str:
    """Order detected boxes top-to-bottom, left-to-right and join into lines."""
    items = []
    for box, text, _ in boxes:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), text))
    items.sort()
    lines: list[list[tuple[float, str]]] = []
    last_y, last_h = None, 0.0
    for y, x, h, text in items:
        if last_y is not None and abs(y - last_y) <= max(h, last_h) * 0.6:
            lines[-1].append((x, text))
        else:
            lines.append([(x, text)])
            last_y, last_h = y, h
    return "\n".join(" ".join(t for _, t in sorted(line)) for line in lines)


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self, min_confidence: float = 0.6):
        from rapidocr_onnxruntime import RapidOCR

        self.engine = RapidOCR()
        self.min_confidence = min_confidence

    def read(self, path: Path) -> OcrResult:
        result, _ = self.engine(str(path))
        if not result:
            return OcrResult("", 0.0)
        kept = [(box, text, float(conf)) for box, text, conf in result if float(conf) >= self.min_confidence and text.strip()]
        if not kept:
            return OcrResult("", 0.0)
        confidence = sum(c for _, _, c in kept) / len(kept)
        return OcrResult(_join_lines(kept), round(confidence, 3))


class TesseractEngine:
    name = "tesseract"

    def __init__(self, min_confidence: float = 0.6):
        import pytesseract  # type: ignore

        pytesseract.get_tesseract_version()  # raises if the binary is missing
        self.pytesseract = pytesseract
        self.min_confidence = min_confidence * 100

    def read(self, path: Path) -> OcrResult:
        from PIL import Image

        with Image.open(path) as image:
            data = self.pytesseract.image_to_data(image.convert("RGB"), output_type=self.pytesseract.Output.DICT)
        words, confs, lines = [], [], {}
        for i, word in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if word.strip() and conf >= self.min_confidence:
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                lines.setdefault(key, []).append(word)
                confs.append(conf)
                words.append(word)
        if not words:
            return OcrResult("", 0.0)
        text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
        return OcrResult(text, round(sum(confs) / len(confs) / 100, 3))


def get_ocr_engine(name: str, min_confidence: float = 0.6) -> OcrEngine:
    if name == "none":
        return NoOcr()
    try:
        if name == "tesseract":
            return TesseractEngine(min_confidence)
        return RapidOcrEngine(min_confidence)
    except Exception as exc:
        log.warning("OCR engine %r unavailable (%s); continuing without OCR", name, exc)
        return NoOcr()
