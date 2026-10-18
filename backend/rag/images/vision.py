"""Optional AI image descriptions with a vision-capable Claude model.

Descriptions are stored separately from extracted metadata (alt text,
captions, OCR) and are always labelled as AI-generated in prompts and in
the UI. The prompt forbids guessing names, dates or facts that are not
visible in the image.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

log = logging.getLogger(__name__)

VISION_PROMPT = (
    "Describe this image from a college website in 1-3 factual sentences for a search index. "
    "Only describe what is clearly visible (setting, objects, activity, visible text). "
    "Do not identify or name people, do not guess locations, dates, events or numbers that are not visibly written, "
    "and do not add opinions. If the image is a logo, icon or decorative graphic, say so briefly."
)


class VisionDescriber:
    def __init__(self, model: str, max_tokens: int = 1024):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def describe(self, path: Path, mime_type: str, context: str = "") -> str:
        import anthropic

        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        prompt = VISION_PROMPT
        if context:
            prompt += f"\n\nPage context (for orientation only, do not repeat unverified claims): {context[:400]}"
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                output_config={"effort": "low"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
        except anthropic.APIStatusError as exc:
            log.warning("Vision description failed for %s: HTTP %s", path.name, exc.status_code)
            return ""
        except anthropic.APIConnectionError as exc:
            log.warning("Vision description failed for %s: %s", path.name, exc)
            return ""
        if response.stop_reason == "refusal":
            return ""
        return " ".join(b.text for b in response.content if b.type == "text").strip()


def get_vision_describer(enabled: bool, model: str) -> VisionDescriber | None:
    if not enabled:
        return None
    try:
        return VisionDescriber(model)
    except Exception as exc:  # missing credentials etc.
        log.warning("Vision descriptions disabled: %s", exc)
        return None
