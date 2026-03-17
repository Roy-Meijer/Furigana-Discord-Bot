import io
import re

import aiohttp
import pytesseract
from pytesseract import Output
from PIL import Image

from bot import log

# image file extensions we want to try text extraction on
IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "bmp")

# try both normal Japanese text extraction and vertical-text extraction
_TEXT_EXTRACTION_CONFIGS = [
    ("jpn", ""),
    ("jpn_vert", "--psm 5"),
]

# match hiragana, katakana, and kanji characters
_RE_JAPANESE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FBF]')

# minimum average OCR confidence (0–100) to treat extracted text as real
# images without text (e.g. photos) score very low; real text typically scores 30+
_MIN_OCR_CONFIDENCE = 20


def image_to_text(image) -> str:
    """Extracts text from an image and returns the result with the most Japanese characters.
    Returns an empty string if OCR confidence is too low (likely not a text image)."""
    best_text, best_score = "", 0

    # try each text extraction configuration and keep the result with the strongest Japanese match
    for lang, config in _TEXT_EXTRACTION_CONFIGS:
        data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=Output.DICT)

        # calculate average confidence, ignoring non-text regions (conf == -1)
        confidences = [c for c in data['conf'] if c != -1]
        if not confidences:
            continue
        avg_conf = sum(confidences) / len(confidences)
        if avg_conf < _MIN_OCR_CONFIDENCE:
            log.debug("Skipping %s result: avg confidence %.1f below threshold", lang, avg_conf)
            continue

        # reconstruct text preserving line breaks via block/paragraph/line grouping
        lines: dict[tuple, list[str]] = {}
        for i, word in enumerate(data['text']):
            if not word.strip():
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            lines.setdefault(key, []).append(word)
        text = "\n".join(" ".join(words) for words in lines.values()).strip()

        score = len(_RE_JAPANESE.findall(text))
        if score > best_score:
            best_text, best_score = text, score

    log.debug("Best text extraction result: %d japanese chars", best_score)
    return best_text


async def extract_text_from_attachments(attachments) -> list[tuple[str, str]]:
    """Downloads supported image attachments and returns extracted text for each one."""
    results = []

    # only keep attachments that look like supported image files
    image_attachments = [a for a in attachments if a.filename.lower().endswith(IMAGE_EXTENSIONS)]
    if not image_attachments:
        return results

    # download each image and extract text from it
    async with aiohttp.ClientSession() as session:
        for attachment in image_attachments:
            log.debug("Downloading image: %s", attachment.filename)
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    # load the downloaded bytes into a PIL image for text extraction
                    data = await resp.read()
                    image = Image.open(io.BytesIO(data))

                    # extract text and keep the filename with the result
                    text = image_to_text(image)
                    log.debug("Text extraction result for %s: %d chars", attachment.filename, len(text))
                    results.append((attachment.filename, text.strip()))
                else:
                    # log download failures so we can debug broken attachments
                    log.error("Failed to download %s: HTTP %d", attachment.filename, resp.status)

    return results