from typing import Final
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level regexes and utility functions
# ---------------------------------------------------------------------------

_RE_KANJI               = re.compile(r'[\u4E00-\u9FBF]')
_RE_DIGITS_BEFORE_KANJI = re.compile(r'(\d+)(?=[\u4E00-\u9FBF])')
_RE_DIGITS              = re.compile(r'\d+')
_RE_HIRAGANA_ONLY       = re.compile(r'[\u3040-\u309F]+$')
_RE_HIRAGANA_SUFFIX     = re.compile(r'[\u3040-\u309Fー]*$')
_RE_KANJI_WORD          = re.compile(r'\d*[\u4E00-\u9FBF]+')
_RE_STRIP_DIGITS        = re.compile(r'\d')

_KANJI_MIN   : Final = 0x4E00
_KANJI_MAX   : Final = 0x9FBF
_KANJI_DIGITS: Final = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

# number kanji excluded from single-character emoji fallback
_NUMBER_KANJI: Final = set('一二三四五六七八九十百千万億兆')

# load reading overrides from external file
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
with open(_DATA_DIR / "reading_overrides.json", "r", encoding="utf-8") as _f:
    _overrides = json.load(_f)

_WORD_READING_OVERRIDES: Final = _overrides.get("word_readings", {})
_READING_CORRECTIONS: Final = _overrides.get("compound_readings", {})
_PREFIX_CORRECTIONS: Final = _overrides.get("prefix_corrections", {})


def _sub_10000(number: int) -> str:
    """Converts a number below 10000 into kanji numerals"""
    parts = []
    if number >= 1000:
        top = number // 1000
        # for 1-9, we say 千, 二千, 三千, etc., but not 一千
        parts.append((_KANJI_DIGITS[top - 1] if top != 1 else '') + '千')
        number %= 1000
    if number >= 100:
        top = number // 100
        # for 1-9, we say 百, 二百, 三百, etc., but not 一百
        parts.append((_KANJI_DIGITS[top - 1] if top != 1 else '') + '百')
        number %= 100
    if number >= 10:
        top = number // 10
        # for 1-9, we say 十, 二十, 三十, etc., but not 一十
        parts.append((_KANJI_DIGITS[top - 1] if top != 1 else '') + '十')
        number %= 10
    if number > 0:
        # for 1-9, we say 一, 二, 三, etc.
        parts.append(_KANJI_DIGITS[number - 1])
    return ''.join(parts)


def arabic_to_kanji(number: int) -> str:
    """Converts an Arabic number into Japanese kanji numerals"""
    number = int(number)
    # for 0 we say 〇, for 1-9999 we use the _sub_10000 function, and for larger numbers we combine 万 and 億 units
    if number == 0:
        return '〇'

    parts = []
    # for 10^8 and above we use the 億 unit
    if number >= 100000000:
        parts.append(_sub_10000(number // 100000000) + '億')
        number %= 100000000
    # for 10^4 and above we use the 万 unit
    if number >= 10000:
        parts.append(_sub_10000(number // 10000) + '万')
        number %= 10000
    # for the rest (1-9999) we convert directly
    if number > 0:
        parts.append(_sub_10000(number))
    return ''.join(parts)


def digits_to_kanji(text: str) -> str:
    """Converts digits to kanji"""
    return _RE_DIGITS_BEFORE_KANJI.sub(lambda m: arabic_to_kanji(m.group()), text)


def _has_furigana(text: str, index: int) -> int:
    """Returns the position after inline furigana like 漢字(かんじ), or 0 if none."""
    # find opening parenthesis immediately following the kanji word
    if index < len(text) and text[index] == '(':
        # find the matching closing parenthesis
        end = text.find(')', index)
        if end != -1:
            content = text[index + 1:end]
            # if the content inside the parentheses is purely hiragana, we skip over it
            if content and _RE_HIRAGANA_ONLY.match(content):
                return end + 1
    return 0


def _sanitize_for_pykakasi(text: str) -> str:
    """Replaces unsupported characters with spaces before passing text to pykakasi."""
    result = []
    # loop though each character
    for ch in text:
        # get the Unicode code point of the character
        cp = ord(ch)
        # check if the character is in a supported range (ASCII, CJK punctuation, hiragana, katakana, kanji, fullwidth forms)
        if (0x20 <= cp <= 0x7E         # ASCII printable
            or 0x3000 <= cp <= 0x303F  # CJK punctuation
            or 0x3040 <= cp <= 0x309F  # hiragana
            or 0x30A0 <= cp <= 0x30FF  # katakana
            or 0x4E00 <= cp <= 0x9FBF  # kanji
            or 0xFF00 <= cp <= 0xFFEF  # fullwidth forms
        ):
            # add character to result if it's supported
            result.append(ch)
        else:
            # replace unsupported characters with a space to preserve text alignment
            result.append(' ')
    return ''.join(result)


# ---------------------------------------------------------------------------
# FuriganaConverter
# ---------------------------------------------------------------------------

class FuriganaConverter:
    """Converts Japanese text to furigana / kanji reading lists using pykakasi."""

    def __init__(self, kks, kanji_emoji: dict) -> None:
        self._kks = kks
        self._kanji_emoji = kanji_emoji

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_inline_furigana(self, text: str) -> str:
        """Generates inline furigana for each line in the given text."""
        result_lines = []
        # loop through each line in the text
        for line in text.split('\n'):
            # keep non-kanji lines unchanged
            if not _RE_KANJI.search(line):
                result_lines.append(line)
                continue

            # convert lines with kanji into inline furigana format
            result_lines.append(self._furigana_line(line))
        return "\n".join(result_lines)

    def get_kanji_list(self, text: str) -> str:
        """Generates a kanji list with readings and optional emoji."""
        # convert text to kanji readings using pykakasi,
        # treating digits before kanji as part of the word (e.g. 3年 -> 三年)
        converted   = self._kks.convert(digits_to_kanji(text))
        seen        = set()
        result_list = []

        # loop all words
        for i, item in enumerate(converted):
            # get the word and the hiragana version
            original, reading = item['orig'], item['hira']

            # Fix pykakasi misparsing 何ですか as 何で(なんで) + すか
            if original == '何で' and reading == 'なんで' and i + 1 < len(converted):
                next_orig = converted[i + 1]['orig']
                if next_orig.startswith('す') or next_orig.startswith('しょ'):
                    original = '何'
                    reading = 'なん'

            # Fix pykakasi misparsing verb+そう (hearsay) as one segment
            elif original.endswith('そ') and reading.endswith('そ') and len(original) > 1:
                trimmed = original[:-1]
                if '\u3040' <= trimmed[-1] <= '\u309F':
                    if i + 1 < len(converted) and converted[i + 1]['orig'].startswith('う'):
                        original = trimmed
                        reading = reading[:-1]

            # Fix reading for kanji+katakana compounds (e.g. 筋トレ → きんトレ)
            if original in _READING_CORRECTIONS and i + 1 < len(converted):
                next_orig = converted[i + 1]['orig']
                for following, correct_reading in _READING_CORRECTIONS[original].items():
                    if next_orig.startswith(following):
                        reading = correct_reading
                        break

            # Fix reading based on preceding segment (e.g. 半+島 → とう)
            if original in _PREFIX_CORRECTIONS and i > 0:
                prev_orig = converted[i - 1]['orig']
                if prev_orig in _PREFIX_CORRECTIONS[original]:
                    reading = _PREFIX_CORRECTIONS[original][prev_orig]

            # Apply direct word reading overrides
            if original in _WORD_READING_OVERRIDES:
                reading = _WORD_READING_OVERRIDES[original]

            # get kanji from the word
            kanji_part = _RE_KANJI_WORD.search(original)
            # ignore if this word has no kanji
            if not kanji_part:
                continue
            kanji_word = kanji_part.group()
            # ignore if we've already processed this kanji word
            if kanji_word in seen:
                continue
            else:
                seen.add(kanji_word)

            display_word = original
            # try to find the original word text
            for match in _RE_KANJI_WORD.finditer(text):
                converted_match = digits_to_kanji(match.group())
                # check if the kanji part matches and the surrounding digits match
                if converted_match == kanji_word or match.group() == kanji_word:
                    # if the kanji part is preceded by digits, include them in the display word
                    trailing = original[kanji_part.end():]
                    display_word = match.group() + trailing
                    break
                # handle case where pykakasi split number from counter (e.g. 二百 from ２００円)
                elif converted_match.startswith(kanji_word) and len(kanji_word) < len(converted_match):
                    # extract just the digit portion from the original match
                    kanji_suffix_len = len(converted_match) - len(kanji_word)
                    display_word = match.group()[:-kanji_suffix_len]
                    break

            # look up emoji for this kanji word
            emoji  = self.get_emoji_for_kanji(display_word)
            suffix = f" {emoji}" if emoji else ""
            # add the kanji word, its reading, and optional emoji to the result list
            result_list.append(f"{display_word} = {reading}{suffix}")

        return "\n".join(result_list)

    def get_emoji_for_kanji(self, word: str) -> str:
        """Looks up the best emoji mapping for a kanji word."""
        kanji_only = _RE_STRIP_DIGITS.sub('', word)

        # check if there is an exact match for this kanji word
        if kanji_only in self._kanji_emoji:
            return self._kanji_emoji[kanji_only]

        # try to find a fuzzy match where the kanji prefix is the same
        # and only the hiragana suffix is different because of conjugation
        best_match = None
        best_score = (-1, 0)
        for candidate, emoji in self._kanji_emoji.items():
            prefix_len = 0

            # count how many characters at the start of both words are the same
            for src_ch, cand_ch in zip(kanji_only, candidate):
                if src_ch != cand_ch:
                    break
                prefix_len += 1

            if prefix_len == 0:
                continue

            src_suffix  = kanji_only[prefix_len:]
            cand_suffix = candidate[prefix_len:]
            # the shared prefix must still contain kanji, otherwise this match is too weak
            if not _RE_KANJI.search(kanji_only[:prefix_len]):
                continue
            # only allow hiragana differences in the suffixes
            if not _RE_HIRAGANA_SUFFIX.fullmatch(src_suffix):
                continue
            if not _RE_HIRAGANA_SUFFIX.fullmatch(cand_suffix):
                continue

            # prefer the longest shared prefix, then prefer the smallest suffix difference
            score = (prefix_len, -(len(src_suffix) + len(cand_suffix)))
            if score > best_score:
                best_match = emoji
                best_score = score

        if best_match:
            return best_match

        # if no word match was found, try matching individual kanji characters
        # (skip number kanji to avoid misleading fallbacks like 一昨日 → 1️⃣)
        for ch in kanji_only:
            if ch in self._kanji_emoji and ch not in _NUMBER_KANJI:
                return self._kanji_emoji[ch]
        return ''

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _furigana_line(self, line: str) -> str:
        """Converts a single line into inline furigana format."""
        # make the line compatible with pykakasi
        sanitized = _sanitize_for_pykakasi(line)
        segments = self._kks.convert(sanitized)

        # map each kanji segment start position to its length and reading
        reading_map: dict[int, tuple[int, str]] = {}
        offset = 0
        for i, segment in enumerate(segments):
            # the length of the original segment in the input text
            orig_seg_len = len(segment['orig'])
            # if this segment contains kanji, add it to the reading map
            if _RE_KANJI.search(segment['orig']):
                orig = segment['orig']
                hira = segment['hira']
                seg_len = orig_seg_len

                # Fix pykakasi misparsing 何ですか as 何で(なんで) + すか
                if orig == '何で' and hira == 'なんで' and i + 1 < len(segments):
                    next_orig = segments[i + 1]['orig']
                    if next_orig.startswith('す') or next_orig.startswith('しょ'):
                        seg_len = 1
                        hira = 'なん'

                # Fix pykakasi misparsing verb+そう (hearsay) as one segment
                # e.g. 違うそう → 違うそ(ちがうそ) + うです → should be 違う(ちがう)
                elif orig.endswith('そ') and hira.endswith('そ') and len(orig) > 1:
                    trimmed = orig[:-1]
                    # only fix if trimmed word ends in hiragana (verb/adj ending)
                    # this avoids false positives on volitional forms like 探そう
                    if '\u3040' <= trimmed[-1] <= '\u309F':
                        if i + 1 < len(segments) and segments[i + 1]['orig'].startswith('う'):
                            seg_len = len(trimmed)
                            hira = hira[:-1]

                # Fix reading for kanji+katakana compounds (e.g. 筋トレ → きんトレ)
                if orig in _READING_CORRECTIONS and i + 1 < len(segments):
                    next_orig = segments[i + 1]['orig']
                    for following, correct_reading in _READING_CORRECTIONS[orig].items():
                        if next_orig.startswith(following):
                            hira = correct_reading
                            break

                # Fix reading based on preceding segment (e.g. 半+島 → とう)
                if orig in _PREFIX_CORRECTIONS and i > 0:
                    prev_orig = segments[i - 1]['orig']
                    if prev_orig in _PREFIX_CORRECTIONS[orig]:
                        hira = _PREFIX_CORRECTIONS[orig][prev_orig]

                # Apply direct word reading overrides
                if orig in _WORD_READING_OVERRIDES:
                    hira = _WORD_READING_OVERRIDES[orig]

                reading_map[offset] = (seg_len, hira)
            offset += orig_seg_len

        parts: list[str] = []
        pos = 0
        # loop through the line and build the result using the reading map
        while pos < len(line):
            # if there is a kanji segment starting at this position
            if pos in reading_map:
                # get the length and reading for this kanji segment, 
                # the original word from the input line, 
                # and the position after this segment
                seg_len, reading = reading_map[pos]
                word = line[pos:pos + seg_len]
                end_pos = pos + seg_len

                # combine digits before kanji into a single reading like 3年 -> 三年
                if parts and _RE_DIGITS.fullmatch(parts[-1]):
                    # collect all consecutive trailing digit parts
                    digit_chars = []
                    while parts and _RE_DIGITS.fullmatch(parts[-1]):
                        digit_chars.append(parts.pop())
                    digit_chars.reverse()
                    digit_part = ''.join(digit_chars)
                    combined_display = digit_part + word
                    combined_kanji = digits_to_kanji(combined_display)
                    # get the reading for the combined kanji word
                    combined_reading = "".join(
                        item['hira'] for item in self._kks.convert(combined_kanji)
                    )
                    # put in correct format
                    parts.append(f"{combined_display}||({combined_reading})||")
                    pos = end_pos
                    continue

                # keep inline furigana already present in the source text
                skip_to = _has_furigana(line, end_pos)
                if skip_to:
                    parts.append(line[pos:skip_to])
                    pos = skip_to
                else:
                    # put in correct format
                    parts.append(f"{word}||({reading})||")
                    pos = end_pos
            else:
                parts.append(line[pos])
                pos += 1

        return "".join(parts)
