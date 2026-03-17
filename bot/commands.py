import io
import json
from collections.abc import Awaitable, Callable, Sequence
import discord
import aiohttp
from discord.ext import commands
from discord import app_commands

from bot import FuriganaBot
from bot.converters import _RE_KANJI
from bot.image_text import extract_text_from_attachments
from bot.views import FuriganaView


FuriganaItem = tuple[str, str]
SendFunc = Callable[..., Awaitable[discord.Message]]


class FuriganaCog(commands.Cog):
    def __init__(self, bot: FuriganaBot):
        self.bot = bot
        # add conntext menu command
        self._context_menu = app_commands.ContextMenu(
            name="ふりがな / Get Furigana",
            callback=self._context_furi,
        )
        self.bot.tree.add_command(self._context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._context_menu.name, type=self._context_menu.type)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_privileged(self, interaction: discord.Interaction) -> bool:
        """Checks if user has permissions to add / remove emojis"""
        if interaction.user.id in self.bot.allowed_user_ids:
            return True
        user_role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
        return bool(user_role_ids & self.bot.allowed_role_ids)

    async def _emoji_word_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Show existing kanji-to-emoji mappings while typing slash commands."""
        if not self._is_privileged(interaction):
            return []

        current_lower = current.lower()
        matches = []
        for word, emoji in self.bot.kanji_emoji.items():
            if current_lower and current_lower not in word.lower() and current_lower not in emoji.lower():
                continue
            matches.append(app_commands.Choice(name=f"{word} -> {emoji}", value=word))
            if len(matches) >= 25:
                break
        return matches

    async def _collect_furigana_items(
        self,
        text: str | None,
        attachments: Sequence[discord.Attachment] | None,
        reference_message: discord.Message | None = None,
    ) -> list[FuriganaItem]:
        """
        Returns a list of (label, text) tuples for each item we want to generate furigana for, in order of priority:
        1) text
        2) attachments
        3) reference message (if no kanji found in 1 and 2)
        """
        # list of tuples with (label, text) for each item we want to generate furigana for
        items = []
        # check the text itself
        if text and _RE_KANJI.search(text):
            items.append(("", text))
        # check attachments
        if attachments:
            for filename, t in await extract_text_from_attachments(attachments):
                if t and _RE_KANJI.search(t):
                    items.append((f"📎 {filename}", t))
        # if there is no kanji in the text or attachments, check the reference message
        if not items and reference_message:
            if reference_message.content and _RE_KANJI.search(reference_message.content):
                items.append(("", reference_message.content))
            if reference_message.attachments:
                for filename, t in await extract_text_from_attachments(reference_message.attachments):
                    if t and _RE_KANJI.search(t):
                        items.append((f"📎 {filename}", t))
        # return list of items
        return items

    async def _send_furigana(
        self,
        send_func: SendFunc,
        furigana_items: list[FuriganaItem],
        content: str | None = None,
        file: discord.File | None = None,
    ) -> None:
        """
        Sends the furigana response message with buttons and stores the generated items,
        so the buttons can still work after the message is sent.
        """
        # create the button view for the message
        view = FuriganaView()
        # collect the arguments we want to pass to the send function
        kwargs = {"view": view}
        if content:
            kwargs["content"] = content
        if file:
            kwargs["file"] = file
        # send the message and keep the returned Discord message object
        msg = await send_func(**kwargs)
        # store the generated items under the sent message id so the buttons can use them later
        self.bot.store.put(msg.id, furigana_items)

    # ------------------------------------------------------------------
    # Prefix commands
    # ------------------------------------------------------------------

    # Supports !furi, !furigana, !ふりがな, !フリガナ
    @commands.command(aliases=["furigana", "ふりがな", "フリガナ"])
    async def furi(self, ctx: commands.Context, *, sentence: str | None = None) -> None:
        """
        Main command to generate furigana for a given sentence or the message content if no sentence is provided.
        Also checks attachments and quoted messages for kanji if the main text does not contain any.
        """
        self.bot.log.info("!furi from %s in #%s", ctx.author, ctx.channel)
        # get the message
        text_to_use = sentence if sentence else ctx.message.content
        ref_message = None
        # get reference message if it exists
        if ctx.message.reference:
            ref_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        # get all furigana items
        furigana_items = await self._collect_furigana_items(
            text=text_to_use,
            attachments=ctx.message.attachments or None,
            reference_message=ref_message,
        )
        # check if there are any items
        if furigana_items:
            self.bot.log.info("Sending %d furigana item(s)", len(furigana_items))
            await self._send_furigana(ctx.send, furigana_items)
        else:
            self.bot.log.debug("No kanji found, nothing to send")

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    @app_commands.command(name="furi", description="Add furigana to Japanese text or image containing Kanji. Use !furi to do both")
    @app_commands.describe(sentence="Japanese text to add furigana to", image="Image containing Japanese text")
    async def slash_furi(
        self,
        interaction: discord.Interaction,
        sentence: str | None = None,
        image: discord.Attachment | None = None,
    ) -> None:
        """Slash command version of !furi. Supports text input and/or image attachment."""
        self.bot.log.info("/furi from %s in #%s", interaction.user, interaction.channel)
        if sentence is None and image is None:
            await interaction.response.send_message("Please provide text, an image, or both.", ephemeral=True)
            return
        await interaction.response.defer()
        attachments    = [image] if image else None
        # get furigana
        furigana_items = await self._collect_furigana_items(text=sentence, attachments=attachments)
        if furigana_items:
            self.bot.log.info("Sending %d furigana item(s)", len(furigana_items))
            file = None
            if image:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image.url) as resp:
                        if resp.status == 200:
                            file = discord.File(io.BytesIO(await resp.read()), filename=image.filename)
            await self._send_furigana(
                lambda **kw: interaction.followup.send(**kw, wait=True),
                furigana_items,
                content=sentence,
                file=file,
            )
        else:
            await interaction.followup.send("No kanji found in the text.", ephemeral=True)
            self.bot.log.debug("No kanji found in the text, nothing to send")

    @app_commands.command(name="emoji_add", description="Map a kanji word to one or more emoji (privileged users only)")
    @app_commands.describe(
        word="The kanji word to add to map (e.g. 猫)",
        emoji="One or more emoji to show next to the reading (e.g. 🐱)",
    )
    @app_commands.autocomplete(word=_emoji_word_autocomplete)
    async def slash_emoji_add(self, interaction: discord.Interaction, word: str, emoji: str) -> None:
        """Add or update a kanji-to-emoji mapping."""
        # autocomplete fills the field with "word -> emoji", strip the suffix
        word = word.split(" -> ")[0]
        # check that privileged user are executing this command
        if not self._is_privileged(interaction):
            await interaction.response.send_message("Only allowed users and roles can use this command.", ephemeral=True)
            return
        # check there is kanji in the word
        if not _RE_KANJI.search(word):
            await interaction.response.send_message(f"`{word}` contains no kanji.", ephemeral=True)
            return
        # find out if we're adding a new mapping or updating an existing one
        previous_emoji = self.bot.kanji_emoji.get(word)
        self.bot.kanji_emoji[word] = emoji
        # add emoji to the json file and reload the in-memory dict
        with open(self.bot.data_dir / "kanji_emoji.json", "w", encoding="utf-8") as f:
            json.dump(self.bot.kanji_emoji, f, ensure_ascii=False, indent=4)
        self.bot.reload_kanji_emoji()
        self.bot.log.info("emoji_add: %s -> %s by %s", word, emoji, interaction.user)
        # feedback message
        if previous_emoji is None:
            await interaction.response.send_message(f"Emoji added: `{word}` -> {emoji}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Emoji updated: `{word}` changed from {previous_emoji} to {emoji}",
                ephemeral=True,
            )

    @app_commands.command(name="emoji_remove", description="Remove an emoji mapping for a kanji word (privileged users only)")
    @app_commands.describe(word="The kanji word to remove the mapping for (e.g. 猫)")
    @app_commands.autocomplete(word=_emoji_word_autocomplete)
    async def slash_emoji_remove(self, interaction: discord.Interaction, word: str) -> None:
        """Removes the mapping for the given kanji word, if it exists."""
        # autocomplete fills the field with "word -> emoji", strip the suffix
        word = word.split(" -> ")[0]
        # check that privileged user are executing this command
        if not self._is_privileged(interaction):
            await interaction.response.send_message("Only allowed users and roles can use this command.", ephemeral=True)
            return
        # check that the mapping exists before trying to remove it
        if word not in self.bot.kanji_emoji:
            await interaction.response.send_message(f"No mapping found for `{word}`.", ephemeral=True)
            return
        # remove the mapping from the in-memory dict
        removed = self.bot.kanji_emoji.pop(word)
        # update the json file and reload the in-memory dict
        with open(self.bot.data_dir / "kanji_emoji.json", "w", encoding="utf-8") as f:
            json.dump(self.bot.kanji_emoji, f, ensure_ascii=False, indent=4)
        self.bot.reload_kanji_emoji()
        self.bot.log.info("emoji_remove: %s (was %s) by %s", word, removed, interaction.user)
        # feedback message
        await interaction.response.send_message(f"Removed mapping for `{word}` (was {removed})", ephemeral=True)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    async def _context_furi(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Context menu command to generate furigana for a specific message."""
        self.bot.log.info("Context menu furi from %s on message %d", interaction.user, message.id)
        await interaction.response.defer()
        # get all furigana items from selected message
        furigana_items = await self._collect_furigana_items(
            text=message.content,
            attachments=message.attachments or None,
        )
        # check if there are any items
        if furigana_items:
            self.bot.log.info("Sending %d furigana item(s)", len(furigana_items))
            await self._send_furigana(
                lambda **kw: interaction.followup.send(**kw, wait=True),
                furigana_items,
            )
        else:
            # send feedback
            await interaction.followup.send("No kanji found in this message.", ephemeral=True)
            self.bot.log.debug("No kanji found in the message, nothing to send")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # load stored furigana items from disk so old buttons still work after a restart
        self.bot.store.load()
        # register the persistent button view with the bot
        self.bot.add_view(FuriganaView())
        # sync slash commands and context menu commands with Discord
        await self.bot.tree.sync()
        # log that the bot finished startup
        self.bot.log.info("Bot ready, persistent view registered, slash commands synced")
