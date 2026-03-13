import discord
from discord.ext import commands
from discord.ui import View, Button
import pykakasi
import re
from PIL import Image
import pytesseract
import io
import aiohttp


intents = discord.Intents.default()
# Bot has read permission
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

kks = pykakasi.kakasi()

async def extract_text_from_attachments(attachments):
    extracted_text = ""
    for attachment in attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ["png", "jpg", "jpeg", "bmp"]):
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        image = Image.open(io.BytesIO(data))
                        # OCR met Japanse taal
                        text = pytesseract.image_to_string(image, lang="jpn")
                        extracted_text += text + "\n"
    return extracted_text.strip()

# Check if word has Kanji
def contains_kanji(word):
    return re.search(r'[\u4E00-\u9FBF]', word)

# Generate Inline Furigana while preserving original text
def get_inline_furigana(text):
    result_text = ""
    index = 0
    while index < len(text):
        char = text[index]
        # check every character for kanji, if found, find the whole cluster and convert to hiragana
        if contains_kanji(char):
            start = index
            while index < len(text) and contains_kanji(text[index]):
                index += 1
            kanji_word = text[start:index]
            # convert to hiragana
            hira = "".join([item['hira'] for item in kks.convert(kanji_word)])
            result_text += f"{kanji_word}({hira})"
        else:
            # keep original text
            result_text += char
            index += 1
    return result_text

# Generate Kanji List Furigana (Kanji = Furigana)
def get_kanji_list(text):
    kanji_words = re.findall(r'[\u4E00-\u9FBF]+', text)
    result_list = []
    for word in kanji_words:
        hira = "".join([item['hira'] for item in kks.convert(word)])
        result_list.append(f"{word} = {hira}")
    return "\n".join(result_list)

# Create a View with two buttons: Inline & List
class FuriganaView(View):
    def __init__(self, original_text):
        super().__init__()
        self.original_text = original_text

    # Inline Furigana button
    @discord.ui.button(label="インライン", style=discord.ButtonStyle.primary, custom_id="show_inline_furigana")
    async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button):
        # send the inline furigana text as ephemeral (only visible to the clicker)
        inline_text = get_inline_furigana(self.original_text)
        await interaction.response.send_message(inline_text, ephemeral=True)

    # List Furigana button
    @discord.ui.button(label="リスト", style=discord.ButtonStyle.secondary, custom_id="show_list")
    async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        # generate kanji list on demand (use original text)
        kanji_list_text = get_kanji_list(self.original_text)
        await interaction.response.send_message(kanji_list_text, ephemeral=True)

# !furi command (slimme keuze: eigen bericht of citaat)
@bot.command()
async def furi(ctx, *, sentence: str = None):
    text_to_use = sentence if sentence else ctx.message.content
    text_has_kanji = contains_kanji(text_to_use)

    furigana_items = []

    # Check attachment
    if ctx.message.attachments:
        attachments_text = await extract_text_from_attachments(ctx.message.attachments)
        for att, text in zip(ctx.message.attachments, attachments_text.split('\n')):
            if contains_kanji(text):
                furigana_items.append((f"<attachment {att.filename}>", text))
        # Use OCR text if no kanji in main message
        if attachments_text:
            for text in attachments_text.split('\n'):
                if contains_kanji(text):
                    text_to_use = text
                    text_has_kanji = True
                    break

    # Only check quoted message if original message has no kanji
    if not text_has_kanji and ctx.message.reference:
        quote_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        # Use quoted message content if it has kanji
        if contains_kanji(quote_message.content):
            text_to_use = quote_message.content
            text_has_kanji = True
        # Check for attachments in quoted message only if still no kanji
        elif quote_message.attachments:
            ref_attachments_text = await extract_text_from_attachments(quote_message.attachments)
            for att, text in zip(quote_message.attachments, ref_attachments_text.split('\n')):
                if contains_kanji(text):
                    furigana_items.append((f"<attachment {att.filename}>", text))

    # Add message itself if it contains kanji and is not empty
    if text_has_kanji and text_to_use.strip():
        furigana_items.insert(0, ("Message", text_to_use))

    if furigana_items:
        class FuriganaViewMulti(View):
            def __init__(self, items):
                super().__init__()
                self.items = items

            @discord.ui.button(label="インライン", style=discord.ButtonStyle.primary, custom_id="show_inline_furigana_multi")
            async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button):
                result = ""
                for label, text in self.items:
                    result += f"{label}: {get_inline_furigana(text)}\n"
                await interaction.response.send_message(result.strip(), ephemeral=True)

            @discord.ui.button(label="リスト", style=discord.ButtonStyle.secondary, custom_id="show_list_multi")
            async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button):
                result = ""
                for label, text in self.items:
                    result += f"{label}:\n{get_kanji_list(text)}\n"
                await interaction.response.send_message(result.strip(), ephemeral=True)

        view = FuriganaViewMulti(furigana_items)
        await ctx.send(view=view)
    else:
        await ctx.send("Geen Japanse tekst gevonden.")

# Read bot token from file
with open("token.txt", "r") as f:
    token = f.read().strip()

# Run the bot
bot.run(token)