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

with open("kanji_emoji.json", "r", encoding="utf-8") as f:
    KANJI_EMOJI = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=["!", "\uff01"], intents=intents)
kks = pykakasi.kakasi()

# Pre-compiled regex patterns
_RE_KANJI = re.compile(r'[\u4E00-\u9FBF]')
_RE_DIGITS_BEFORE_KANJI = re.compile(r'(\d+)(?=[\u4E00-\u9FBF])')
_RE_DIGITS = re.compile(r'\d+')
_RE_HIRAGANA_ONLY = re.compile(r'[\u3040-\u309F]+$')
_RE_KANJI_WORD = re.compile(r'\d*[\u4E00-\u9FBF]+')
_RE_STRIP_DIGITS = re.compile(r'\d')
_KANJI_MIN, _KANJI_MAX = 0x4E00, 0x9FBF

def _is_kanji(ch):
    return _KANJI_MIN <= ord(ch) <= _KANJI_MAX

KANJI_DIGITS = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

def _sub_10000(n):
    """Convert a number 0-9999 to kanji."""
    parts = []
    if n >= 1000:
        t = n // 1000
        parts.append(('' if t == 1 else KANJI_DIGITS[t - 1]) + '千')
        n %= 1000
    if n >= 100:
        h = n // 100
        parts.append(('' if h == 1 else KANJI_DIGITS[h - 1]) + '百')
        n %= 100
    if n >= 10:
        t = n // 10
        parts.append(('' if t == 1 else KANJI_DIGITS[t - 1]) + '十')
        n %= 10
    if n > 0:
        parts.append(KANJI_DIGITS[n - 1])
    return ''.join(parts)

def arabic_to_kanji(n):
    """Convert an Arabic number string to proper Japanese kanji (e.g. '10' -> '十', '300' -> '三百')"""
    n = int(n)
    if n == 0:
        return '〇'
    parts = []
    if n >= 100000000:
        top = n // 100000000
        parts.append(_sub_10000(top) + '億')
        n %= 100000000
    if n >= 10000:
        top = n // 10000
        parts.append(_sub_10000(top) + '万')
        n %= 10000
    if n > 0:
        parts.append(_sub_10000(n))
    return ''.join(parts)

def digits_to_kanji(text):
    """Convert Arabic numbers to kanji when followed by kanji (e.g. '300匹' -> '三百匹')"""
    return _RE_DIGITS_BEFORE_KANJI.sub(lambda m: arabic_to_kanji(m.group()), text)

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

def contains_kanji(text):
    return _RE_KANJI.search(text)

def has_furigana(text, index):
    """Check if position is followed by (hiragana), returning end index or 0."""
    if index < len(text) and text[index] == '(':
        end = text.find(')', index)
        if end != -1:
            content = text[index + 1:end]
            if content and _RE_HIRAGANA_ONLY.match(content):
                return end + 1
    return 0

def get_inline_furigana(text):
    parts = []
    i = 0
    n = len(text)
    while i < n:
        digit_match = _RE_DIGITS.match(text, i)
        if digit_match and digit_match.end() < n and _is_kanji(text[digit_match.end()]):
            start = i
            i = digit_match.end()
            while i < n and _is_kanji(text[i]):
                i += 1
            skip_to = has_furigana(text, i)
            if skip_to:
                parts.append(text[start:skip_to])
                i = skip_to
            else:
                word = text[start:i]
                hira = "".join(item['hira'] for item in kks.convert(digits_to_kanji(word)))
                parts.append(f"{word}({hira})")
        elif _is_kanji(text[i]):
            start = i
            i += 1
            while i < n and _is_kanji(text[i]):
                i += 1
            skip_to = has_furigana(text, i)
            if skip_to:
                parts.append(text[start:skip_to])
                i = skip_to
            else:
                word = text[start:i]
                hira = "".join(item['hira'] for item in kks.convert(word))
                parts.append(f"{word}({hira})")
        else:
            parts.append(text[i])
            i += 1
    return "".join(parts)

def get_emoji_for_kanji(word):
    """Look up emoji: try full word first, then individual characters."""
    kanji_only = _RE_STRIP_DIGITS.sub('', word)
    if kanji_only in KANJI_EMOJI:
        return KANJI_EMOJI[kanji_only]
    for char in kanji_only:
        if char in KANJI_EMOJI:
            return KANJI_EMOJI[char]
    return ''

def get_kanji_list(text):
    converted = kks.convert(digits_to_kanji(text))
    seen = set()
    result_list = []
    for item in converted:
        orig, hira = item['orig'], item['hira']
        if not contains_kanji(orig):
            continue
        kanji_part = _RE_KANJI_WORD.search(orig)
        if not kanji_part:
            continue
        kanji_word = kanji_part.group()
        if kanji_word in seen:
            continue
        seen.add(kanji_word)
        display_word, display_hira = orig, hira
        for m in _RE_KANJI_WORD.finditer(text):
            if digits_to_kanji(m.group()) == kanji_word or m.group() == kanji_word:
                trailing = orig[kanji_part.end():]
                display_word = m.group() + trailing
                break
        emoji = get_emoji_for_kanji(display_word)
        suffix = f" {emoji}" if emoji else ""
        result_list.append(f"{display_word} = {display_hira}{suffix}")
    return "\n".join(result_list)

@bot.command(aliases=["ふり", "フリ", "ふりがな", "フリガナ", "furigana"])
async def furi(ctx, *, sentence: str = None):
    furigana_items = []

    text_to_use = sentence if sentence else ctx.message.content
    if text_to_use and contains_kanji(text_to_use):
        furigana_items.append((None, text_to_use))

    if ctx.message.attachments:
        attachment_results = await extract_text_from_attachments(ctx.message.attachments)
        for filename, text in attachment_results:
            if text and contains_kanji(text):
                furigana_items.append((f"📎 {filename}", text))

    # Fallback to quoted message if nothing found above
    if not furigana_items and ctx.message.reference:
        quote_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if quote_message.content and contains_kanji(quote_message.content):
            furigana_items.append((None, quote_message.content))
        if quote_message.attachments:
            ref_attachment_results = await extract_text_from_attachments(quote_message.attachments)
            for filename, text in ref_attachment_results:
                if text and contains_kanji(text):
                    furigana_items.append((f"📎 {filename} (引用)", text))

    if furigana_items:
        class FuriganaViewMulti(View):
            def __init__(self, items):
                super().__init__()
                self.items = items

            @discord.ui.button(label="ふりがな付き", style=discord.ButtonStyle.primary, custom_id="show_inline_furigana_multi")
            async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button):
                parts = []
                for label, text in self.items:
                    if label:
                        parts.append(f"**{label}**\n{get_inline_furigana(text)}")
                    else:
                        parts.append(get_inline_furigana(text))
                await interaction.response.send_message("\n\n".join(parts), ephemeral=True)

            @discord.ui.button(label="漢字リスト", style=discord.ButtonStyle.success, custom_id="show_list_multi")
            async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button):
                parts = []
                for label, text in self.items:
                    if label:
                        parts.append(f"**{label}**\n{get_kanji_list(text)}")
                    else:
                        parts.append(get_kanji_list(text))
                await interaction.response.send_message("\n\n".join(parts), ephemeral=True)

        view = FuriganaViewMulti(furigana_items)
        await ctx.send(view=view)

with open("token.txt", "r") as f:
    token = f.read().strip()
bot.run(token)