from typing import *
import discord
from discord.ext import commands
from discord.ui import View
import pykakasi
import re
import json
import io
import aiohttp
from PIL import Image
import pytesseract

# load kanji to emoji mapping
with open("kanji_emoji.json", "r", encoding="utf-8") as f:
    KANJI_EMOJI = json.load(f)

intents                 = discord.Intents.default()
intents.message_content = True
bot                     = commands.Bot(command_prefix=["!", "\uff01"], intents=intents)
kks                     = pykakasi.kakasi()

# regex patterns
_RE_KANJI               = re.compile(r'[\u4E00-\u9FBF]')
_RE_DIGITS_BEFORE_KANJI = re.compile(r'(\d+)(?=[\u4E00-\u9FBF])')
_RE_DIGITS              = re.compile(r'\d+')
_RE_HIRAGANA_ONLY       = re.compile(r'[\u3040-\u309F]+$')
_RE_KANJI_WORD          = re.compile(r'\d*[\u4E00-\u9FBF]+')
_RE_STRIP_DIGITS        = re.compile(r'\d')

_KANJI_MIN              : Final = 0x4E00
_KANJI_MAX              : Final = 0x9FBF
_KANJI_DIGITS           : Final = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

# checks if a character is kanji
def _is_kanji(ch):
    return _KANJI_MIN <= ord(ch) <= _KANJI_MAX

# convert 0 - 9999 to kanji
def _sub_10000(number: int):
    parts = []
    if number >= 1000:
        top = number // 1000
        if top != 1:
            parts.append(_KANJI_DIGITS[top - 1] + '千')
        else:
            parts.append('千')
        number %= 1000
    if number >= 100:
        top = number // 100
        if top != 1:
            parts.append(_KANJI_DIGITS[top - 1] + '百')
        else:
            parts.append('百')
        number %= 100
    if number >= 10:
        top = number // 10
        if top != 1:
            parts.append(_KANJI_DIGITS[top - 1] + '十')
        else:
            parts.append('十')
        number %= 10
    if number > 0:
        parts.append(_KANJI_DIGITS[number - 1])
    return ''.join(parts)

# convert arabic numbers to kanji
def arabic_to_kanji(number):
    number = int(number)
    if number == 0:
        return '〇'
    parts = []
    if number >= 100000000:
        hundred_millions = number // 100000000
        parts.append(_sub_10000(hundred_millions) + '億')
        number %= 100000000
    if number >= 10000:
        ten_thousands = number // 10000
        parts.append(_sub_10000(ten_thousands) + '万')
        number %= 10000
    if number > 0:
        parts.append(_sub_10000(number))
    return ''.join(parts)

# convert arabic number followed by kanji to kanji (eg 3日 to 三日)
def digits_to_kanji(text):
    return _RE_DIGITS_BEFORE_KANJI.sub(lambda m: arabic_to_kanji(m.group()), text)

# extract japanese text from image
IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "bmp")
def ocr_image(image):
    return pytesseract.image_to_string(image, lang="jpn").strip()
async def extract_text_from_attachments(attachments):
    results = []
    image_attachments = [a for a in attachments if a.filename.lower().endswith(IMAGE_EXTENSIONS)]
    if not image_attachments:
        return results
    async with aiohttp.ClientSession() as session:
        for attachment in image_attachments:
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    image = Image.open(io.BytesIO(data))
                    text = ocr_image(image)
                    results.append((attachment.filename, text.strip()))
    return results

# checks if some text contains kanji
def contains_kanji(text):
    return _RE_KANJI.search(text)

# checks if there is furigana already
def has_furigana(text, index):
    if index < len(text) and text[index] == '(':
        end = text.find(')', index)
        if end != -1:
            content = text[index + 1:end]
            if content and _RE_HIRAGANA_ONLY.match(content):
                return end + 1
    return 0

# replaces anything pykakasi can't handle with a space (preserves length)
def _sanitize_for_pykakasi(text):
    result = []
    for ch in text:
        cp = ord(ch)
        if (0x20 <= cp <= 0x7E        # ASCII printable
            or 0x3000 <= cp <= 0x303F # CJK punctuation
            or 0x3040 <= cp <= 0x309F # hiragana
            or 0x30A0 <= cp <= 0x30FF # katakana
            or 0x4E00 <= cp <= 0x9FBF # kanji
            or 0xFF00 <= cp <= 0xFFEF # fullwidth forms
        ):
            result.append(ch)
        else:
            result.append(' ')
    return ''.join(result)

# convert a piece of text to inline furigana format
# processes line by line so URLs/blank lines don't break pykakasi
# uses full-line pykakasi for accurate context-aware readings (eg 美味しい = おいしい)
def get_inline_furigana(text):
    result_lines = []
    for line in text.split('\n'):
        if not contains_kanji(line):
            result_lines.append(line)
            continue
        # sanitize emoji so pykakasi doesn't change text length
        sanitized   = _sanitize_for_pykakasi(line)
        segments    = kks.convert(sanitized)
        # build offset → (length, reading) map from pykakasi output
        reading_map = {}
        offset      = 0
        for segment in segments:
            seg_len = len(segment['orig'])
            if contains_kanji(segment['orig']):
                reading_map[offset] = (seg_len, segment['hira'])
            offset += seg_len
        # walk the ORIGINAL line using the reading map
        parts = []
        pos   = 0
        while pos < len(line):
            if pos in reading_map:
                seg_len, reading = reading_map[pos]
                word    = line[pos:pos + seg_len]
                end_pos = pos + seg_len
                # check for digits right before this kanji segment (eg "300匹")
                if parts and _RE_DIGITS.fullmatch(parts[-1]):
                    digit_part       = parts.pop()
                    combined_display = digit_part + word
                    combined_kanji   = digits_to_kanji(combined_display)
                    combined_reading = "".join(item['hira'] for item in kks.convert(combined_kanji))
                    parts.append(f"{combined_display}||({combined_reading})||")
                    pos = end_pos
                    continue
                # skip if furigana already exists after this word
                skip_to = has_furigana(line, end_pos)
                if skip_to:
                    parts.append(line[pos:skip_to])
                    pos = skip_to
                else:
                    parts.append(f"{word}||({reading})||")
                    pos = end_pos
            else:
                parts.append(line[pos])
                pos += 1
        result_lines.append("".join(parts))
    return "\n".join(result_lines)

# look up emoji for a kanji word, try full word first, then individual characters
def get_emoji_for_kanji(word):
    kanji_only = _RE_STRIP_DIGITS.sub('', word)
    if kanji_only in KANJI_EMOJI:
        return KANJI_EMOJI[kanji_only]
    for character in kanji_only:
        if character in KANJI_EMOJI:
            return KANJI_EMOJI[character]
    return ''

# convert text to a deduplicated kanji reading list with emoji
def get_kanji_list(text):
    converted   = kks.convert(digits_to_kanji(text))
    seen        = set()
    result_list = []
    for item in converted:
        original, reading = item['orig'], item['hira']
        if not contains_kanji(original):
            continue
        # extract the kanji part of the word
        kanji_part = _RE_KANJI_WORD.search(original)
        if not kanji_part:
            continue
        kanji_word = kanji_part.group()
        # skip duplicates
        if kanji_word in seen:
            continue
        seen.add(kanji_word)
        # find the original form in the source text (preserves arabic digits)
        display_word, display_reading = original, reading
        for match in _RE_KANJI_WORD.finditer(text):
            if digits_to_kanji(match.group()) == kanji_word or match.group() == kanji_word:
                trailing     = original[kanji_part.end():]
                display_word = match.group() + trailing
                break
        # add emoji suffix if available
        emoji  = get_emoji_for_kanji(display_word)
        suffix = f" {emoji}" if emoji else ""
        result_list.append(f"{display_word} = {display_reading}{suffix}")
    return "\n".join(result_list)

# !furi command: check message text, attachments, then fallback to quoted message
@bot.command(aliases=["ふり", "フリ", "ふりがな", "フリガナ", "furigana"])
async def furi(ctx, *, sentence: str = None):
    furigana_items = []

    # step 1: check the message text itself
    text_to_use = sentence if sentence else ctx.message.content
    if text_to_use and contains_kanji(text_to_use):
        furigana_items.append((None, text_to_use))

    # step 2: check attached images for japanese text (OCR)
    if ctx.message.attachments:
        attachment_results = await extract_text_from_attachments(ctx.message.attachments)
        for filename, text in attachment_results:
            if text and contains_kanji(text):
                furigana_items.append((f"📎 {filename}", text))

    # step 3: fallback to quoted/replied message if nothing found above
    if not furigana_items and ctx.message.reference:
        quote_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if quote_message.content and contains_kanji(quote_message.content):
            furigana_items.append((None, quote_message.content))
        if quote_message.attachments:
            ref_attachment_results = await extract_text_from_attachments(quote_message.attachments)
            for filename, text in ref_attachment_results:
                if text and contains_kanji(text):
                    furigana_items.append((f"📎 {filename} (引用)", text))

    # show buttons if we found any kanji text
    if furigana_items:
        view         = FuriganaView(furigana_items)
        view.message = await ctx.send(view=view)


class FuriganaView(View):
    def __init__(self, items):
        super().__init__(timeout=1209600)
        self.items   = items
        self.message = None

    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
            button.style    = discord.ButtonStyle.secondary
        if self.message:
            await self.message.edit(view=self)

    # blue button for inline furigana
    @discord.ui.button(label="ふりがな付き", style=discord.ButtonStyle.primary)
    async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button):
        parts = []
        for label, text in self.items:
            if label:
                parts.append(f"**{label}**\n{get_inline_furigana(text)}")
            else:
                parts.append(get_inline_furigana(text))
        await interaction.response.send_message("\n\n".join(parts), ephemeral=True)

    # green button for kanji list
    @discord.ui.button(label="漢字リスト", style=discord.ButtonStyle.success)
    async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        parts = []
        for label, text in self.items:
            if label:
                parts.append(f"**{label}**\n{get_kanji_list(text)}")
            else:
                parts.append(get_kanji_list(text))
        await interaction.response.send_message("\n\n".join(parts), ephemeral=True)

with open("../bot_token.txt", "r") as f:
    token = f.read().strip()
bot.run(token)