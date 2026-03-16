import discord
from discord.ui import View

from bot import log, converter, store


class FuriganaView(View):
    """Persistent Discord view containing the furigana action buttons."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="ふりがな付き", style=discord.ButtonStyle.primary, custom_id="furigana_inline")
    async def show_inline_furigana(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Shows inline furigana for the stored text items."""
        log.info("Inline furigana button clicked by %s", interaction.user)
        # get the stored items for the message this button belongs to
        items = store.get(interaction.message.id)
        if not items:
            # send feedback if the stored data is no longer available
            await interaction.response.send_message(
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

            # send the result to the user who clicked the button
            await interaction.response.send_message("\n\n".join(parts), ephemeral=True)
        except Exception:
            log.error("Inline furigana failed", exc_info=True)

    @discord.ui.button(label="漢字リスト", style=discord.ButtonStyle.success, custom_id="furigana_list")
    async def show_kanji_list(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Shows a kanji list with readings for the stored text items."""
        log.info("Kanji list button clicked by %s", interaction.user)
        # get the stored items for the message this button belongs to
        items = store.get(interaction.message.id)
        if not items:
            # send feedback if the stored data is no longer available
            await interaction.response.send_message(
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

            # send the result to the user who clicked the button
            await interaction.response.send_message("\n\n".join(parts), ephemeral=True)
        except Exception:
            log.error("Kanji list failed", exc_info=True)
