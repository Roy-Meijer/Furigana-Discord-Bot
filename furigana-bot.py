import discord
from discord.ext import commands
from discord.ui import View, Button
import pykakasi
import re

intents = discord.Intents.default()
# Bot has read permission
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

kks = pykakasi.kakasi()

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
    # Als de gebruiker geen tekst meegeeft in !furi, probeer de eigen content te gebruiken
    text_to_use = sentence if sentence else ctx.message.content
    text_has_kanji = contains_kanji(text_to_use)

    # Als er geen Japanse tekens in het bericht zitten en er is een reply
    if not text_has_kanji and ctx.message.reference:
        # Haal het geciteerde bericht
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        text_to_use = ref_msg.content
        text_has_kanji = contains_kanji(text_to_use)

    # Nu heb je de juiste tekst (eigen bericht of citaat)
    if text_has_kanji:
        view = FuriganaView(text_to_use)
        await ctx.send(view=view)

# Read bot token from file
with open("token.txt", "r") as f:
    token = f.read().strip()

# Run the bot
bot.run(token)