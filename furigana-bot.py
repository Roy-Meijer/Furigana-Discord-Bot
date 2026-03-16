from typing import *
import discord
from discord.ext import commands
from discord.ui import View
import pykakasi
import re
import json
import io
import logging
from logging.handlers import RotatingFileHandler
import aiohttp
from PIL import Image
import pytesseract

# logging setup: 5MB per file, keep 3 backups (20MB max total)
log = logging.getLogger("furigana-bot")
log.setLevel(logging.DEBUG)
_handler = RotatingFileHandler("furigana-bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
log.addHandler(_handler)

# load kanji to emoji mapping
with open("kanji_emoji.json", "r", encoding="utf-8") as f:
    KANJI_EMOJI = json.load(f)
log.info("Loaded %d kanji emoji mappings", len(KANJI_EMOJI))

intents                 = discord.Intents.default()
intents.message_content = True
bot                     = commands.Bot(command_prefix=["!", "\uff01"], intents=intents)
kks                     = pykakasi.kakasi()

# persistent store: message_id → items, so buttons survive bot restarts
STORE_FILE      = "furigana_store.json"
_furigana_store = {}

def _load_store():
    global _furigana_store
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            _furigana_store = {int(k): v for k, v in json.load(f).items()}
        log.info("Loaded %d stored furigana items", len(_furigana_store))
    except FileNotFoundError:
        _furigana_store = {}

def _save_store():
    # keep only the latest 100000 entries to prevent unbounded growth
    if len(_furigana_store) > 100000:
        keys = sorted(_furigana_store)
        for k in keys[:-100000]:
            del _furigana_store[k]
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in _furigana_store.items()}, f, ensure_ascii=False)

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
_OCR_CONFIGS = [
    ("jpn",      ""),        # horizontal auto
    ("jpn_vert", "--psm 5"), # vertical block
]
_RE_JAPANESE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FBF]')
def ocr_image(image):
    best_text, best_score = "", 0
    for lang, config in _OCR_CONFIGS:
        text  = pytesseract.image_to_string(image, lang=lang, config=config).strip()
        score = len(_RE_JAPANESE.findall(text))
        if score > best_score:
            best_text, best_score = text, score
    log.debug("Tesseract best: %d japanese chars", best_score)
    return best_text
async def extract_text_from_attachments(attachments):
    results = []
    image_attachments = [a for a in attachments if a.filename.lower().endswith(IMAGE_EXTENSIONS)]
    if not image_attachments:
        return results
    async with aiohttp.ClientSession() as session:
        for attachment in image_attachments:
            log.debug("Downloading image: %s", attachment.filename)
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    image = Image.open(io.BytesIO(data))
                    text = ocr_image(image)
                    log.debug("OCR result for %s: %d chars", attachment.filename, len(text))
                    results.append((attachment.filename, text.strip()))
                else:
                    log.error("Failed to download %s: HTTP %d", attachment.filename, resp.status)
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

# shared: collect furigana items from text, attachments, and optional reference message
async def _collect_furigana_items(text=None, attachments=None, reference_message=None):
    items = []
    if text and contains_kanji(text):
        items.append((None, text))
    if attachments:
        attachment_results = await extract_text_from_attachments(attachments)
        for filename, t in attachment_results:
            if t and contains_kanji(t):
                items.append((f"📎 {filename}", t))
    if not items and reference_message:
        if reference_message.content and contains_kanji(reference_message.content):
            items.append((None, reference_message.content))
        if reference_message.attachments:
            ref_results = await extract_text_from_attachments(reference_message.attachments)
            for filename, t in ref_results:
                if t and contains_kanji(t):
                    items.append((f"📎 {filename} (引用)", t))
    return items

# shared: send furigana buttons and store data
async def _send_furigana(send_func, furigana_items, content=None, file=None):
    view = FuriganaView()
    kwargs = {"view": view}
    if content:
        kwargs["content"] = content
    if file:
        kwargs["file"] = file
    msg = await send_func(**kwargs)
    _furigana_store[msg.id] = furigana_items
    _save_store()

# !furi command: check message text, attachments, then fallback to quoted message
@bot.command(aliases=["ふり", "フリ", "ふりがな", "フリガナ", "furigana"])
async def furi(ctx, *, sentence: str = None):
    log.info("!furi from %s in #%s", ctx.author, ctx.channel)
    text_to_use = sentence if sentence else ctx.message.content
    ref_message = None
    if ctx.message.reference:
        ref_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    furigana_items = await _collect_furigana_items(
        text=text_to_use,
        attachments=ctx.message.attachments or None,
        reference_message=ref_message
    )
    if furigana_items:
        log.info("Sending %d furigana item(s)", len(furigana_items))
        await _send_furigana(ctx.send, furigana_items)
    else:
        log.debug("No kanji found, nothing to send")

# /furi slash command
@bot.tree.command(name="furi", description="Add furigana readings to Japanese text")
@discord.app_commands.describe(sentence="Japanese text to add furigana to", image="Image containing Japanese text (OCR)")
async def slash_furi(interaction: discord.Interaction, sentence: str = None, image: discord.Attachment = None):
    log.info("/furi from %s in #%s", interaction.user, interaction.channel)
    await interaction.response.defer()
    attachments = [image] if image else None
    furigana_items = await _collect_furigana_items(text=sentence, attachments=attachments)
    if furigana_items:
        log.info("Sending %d furigana item(s)", len(furigana_items))
        file = None
        if image:
            async with aiohttp.ClientSession() as session:
                async with session.get(image.url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        file = discord.File(io.BytesIO(data), filename=image.filename)
        await _send_furigana(lambda **kw: interaction.followup.send(**kw, wait=True), furigana_items, content=sentence, file=file)
    else:
        await interaction.followup.send("No kanji found in the text.", ephemeral=True)

# right-click message → Apps → get furigana
@bot.tree.context_menu(name="get furigana")
async def context_furi(interaction: discord.Interaction, message: discord.Message):
    log.info("Context menu furi from %s on message %d", interaction.user, message.id)
    await interaction.response.defer()
    furigana_items = await _collect_furigana_items(
        text=message.content,
        attachments=message.attachments or None
    )
    if furigana_items:
        log.info("Sending %d furigana item(s)", len(furigana_items))
        await _send_furigana(lambda **kw: interaction.followup.send(**kw, wait=True), furigana_items)
    else:
        await interaction.followup.send("No kanji found in this message.", ephemeral=True)


class FuriganaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    # blue button for inline furigana
    @discord.ui.button(label="ふりがな付き", style=discord.ButtonStyle.primary, custom_id="furigana_inline")
    async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button):
        log.info("Inline furigana button clicked by %s", interaction.user)
        items = _furigana_store.get(interaction.message.id)
        if not items:
            await interaction.response.send_message("This data has expired. Reply to the original message with `!furi` to generate new buttons!", ephemeral=True)
            return
        try:
            parts = []
            for label, text in items:
                if label:
                    parts.append(f"**{label}**\n{get_inline_furigana(text)}")
                else:
                    parts.append(get_inline_furigana(text))
            await interaction.response.send_message("\n\n".join(parts), ephemeral=True)
        except Exception:
            log.error("Inline furigana failed", exc_info=True)

    # green button for kanji list
    @discord.ui.button(label="漢字リスト", style=discord.ButtonStyle.success, custom_id="furigana_list")
    async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        log.info("Kanji list button clicked by %s", interaction.user)
        items = _furigana_store.get(interaction.message.id)
        if not items:
            await interaction.response.send_message("This data has expired. Reply to the original message with `!furi` to generate new buttons!", ephemeral=True)
            return
        try:
            parts = []
            for label, text in items:
                if label:
                    parts.append(f"**{label}**\n{get_kanji_list(text)}")
                else:
                    parts.append(get_kanji_list(text))
            await interaction.response.send_message("\n\n".join(parts), ephemeral=True)
        except Exception:
            log.error("Kanji list failed", exc_info=True)


@bot.event
async def on_ready():
    _load_store()
    bot.add_view(FuriganaView())
    await bot.tree.sync()
    log.info("Bot ready, persistent view registered, slash commands synced")

with open("../bot_token.txt", "r") as f:
    token = f.read().strip()
log.info("Starting bot")
bot.run(token)