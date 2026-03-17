import discord
from discord.ui import View

from bot import log, converter, store

_MAX_LEN = 2000


def _chunk_message(text: str) -> list[str]:
    """Splits text into chunks of at most _MAX_LEN characters, preferring splits at double newlines."""
    if len(text) <= _MAX_LEN:
        return [text]
    chunks = []
    while len(text) > _MAX_LEN:
        # try to find a double newline to split at within the limit
        split_at = text.rfind("\n\n", 0, _MAX_LEN)
        if split_at == -1:
            # fall back to a single newline
            split_at = text.rfind("\n", 0, _MAX_LEN)
        if split_at == -1:
            # hard cut if no newline found
            split_at = _MAX_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def _send_ephemeral(interaction: discord.Interaction, content: str) -> None:
    """Sends an ephemeral reply, splitting into followup messages if over the 2000 char limit."""
    chunks = _chunk_message(content)
    for chunk in chunks:
        await interaction.followup.send(chunk, ephemeral=True)

class FuriganaView(View):
    """Persistent Discord view containing the furigana action buttons."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="ふりがな付き", style=discord.ButtonStyle.primary, custom_id="furigana_inline")
    async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Shows inline furigana for the stored text items."""
        log.info("Inline furigana button clicked by %s", interaction.user)
        await interaction.response.defer(ephemeral=True)
        # get the stored items for the message this button belongs to
        items = store.get(interaction.message.id)
        if not items:
            # send feedback if the stored data is no longer available
            await interaction.followup.send(
                "This data has expired. Use `!furi`, `/furi`, or the `get furigana` context menu on the original message to generate new buttons!",
                ephemeral=True,
            )
            return

        try:
            parts = []
            # convert each stored item into inline furigana text
            for label, text in items:
                if label:
                    parts.append(f"**{label}**\n{converter.get_inline_furigana(text)}")
                else:
                    parts.append(converter.get_inline_furigana(text))

            # send the result to the user who clicked the button (may split into multiple messages)
            await _send_ephemeral(interaction, "\n\n".join(parts))
        except Exception:
            log.error("Inline furigana failed", exc_info=True)

    @discord.ui.button(label="漢字リスト", style=discord.ButtonStyle.success, custom_id="furigana_list")
    async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Shows a kanji list with readings for the stored text items."""
        log.info("Kanji list button clicked by %s", interaction.user)
        await interaction.response.defer(ephemeral=True)
        # get the stored items for the message this button belongs to
        items = store.get(interaction.message.id)
        if not items:
            # send feedback if the stored data is no longer available
            await interaction.followup.send(
                "This data has expired. Use `!furi`, `/furi`, or the `get furigana` context menu on the original message to generate new buttons!",
                ephemeral=True,
            )
            return

        try:
            parts = []
            # convert each stored item into a kanji list
            for label, text in items:
                if label:
                    parts.append(f"**{label}**\n{converter.get_kanji_list(text)}")
                else:
                    parts.append(converter.get_kanji_list(text))

            # send the result to the user who clicked the button (may split into multiple messages)
            await _send_ephemeral(interaction, "\n\n".join(parts))
        except Exception:
            log.error("Kanji list failed", exc_info=True)
