import discord
from discord.ext import commands
import pykakasi
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging and shared paths
# ---------------------------------------------------------------------------

# keep log files small and rotate them automatically
log = logging.getLogger("furigana-bot")
log.setLevel(logging.DEBUG)
_handler = RotatingFileHandler("furigana-bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
log.addHandler(_handler)

# data directory for json files used by the bot
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Allowed users and roles
# ---------------------------------------------------------------------------

# allowed_users.txt — who may use privileged commands (emoji_add / emoji_remove)
# Lines starting with # are comments and are ignored.
# user:<id>   — grants access to that specific Discord user
# role:<id>   — grants access to anyone who has that Discord role
ALLOWED_USER_IDS: set[int] = set()
ALLOWED_ROLE_IDS: set[int] = set()

try:
    with open("allowed_users.txt", "r") as _f:
        # parse each line and populate the allowed user and role ID sets
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if _line.startswith("user:"):
                ALLOWED_USER_IDS.add(int(_line[5:].strip()))
            elif _line.startswith("role:"):
                ALLOWED_ROLE_IDS.add(int(_line[5:].strip()))

    log.info("Loaded %d allowed user(s) and %d allowed role(s)", len(ALLOWED_USER_IDS), len(ALLOWED_ROLE_IDS))
except FileNotFoundError:
    log.warning("allowed_users.txt not found — no users or roles can use privileged commands")

# ---------------------------------------------------------------------------
# Shared data and helper instances
# ---------------------------------------------------------------------------

# load the kanji-to-emoji mapping from disk
with open(DATA_DIR / "kanji_emoji.json", "r", encoding="utf-8") as f:
    KANJI_EMOJI: dict = json.load(f)
log.info("Loaded %d kanji emoji mappings", len(KANJI_EMOJI))

# shared kakasi instance used for furigana conversion
kks = pykakasi.kakasi()

# import after dependencies are ready so these classes can use the shared instances above
from bot.store import FuriganaStore          # noqa: E402
from bot.converters import FuriganaConverter  # noqa: E402

# shared store and converter instances used across the bot
store = FuriganaStore(DATA_DIR / "furigana_store.json")
converter = FuriganaConverter(kks, KANJI_EMOJI)


class FuriganaBot(commands.Bot):
    """Custom bot class that keeps shared bot state in one place."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # shared logger, paths, and helper instances
        self.log = log
        self.data_dir = DATA_DIR
        self.store = store
        self.converter = converter

        # allowed users / roles for privileged commands
        self.allowed_user_ids = ALLOWED_USER_IDS
        self.allowed_role_ids = ALLOWED_ROLE_IDS

        # shared kanji-to-emoji mapping
        self.kanji_emoji = KANJI_EMOJI

    def reload_kanji_emoji(self) -> None:
        """Reloads kanji_emoji.json and updates the in-memory dict in-place."""
        # read the latest mapping from disk
        with open(self.data_dir / "kanji_emoji.json", "r", encoding="utf-8") as f:
            fresh = json.load(f)

        # update the shared dict in place so existing references stay valid
        self.kanji_emoji.clear()
        self.kanji_emoji.update(fresh)
        self.log.info("Reloaded %d kanji emoji mappings", len(self.kanji_emoji))


# ---------------------------------------------------------------------------
# Bot instance
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = FuriganaBot(command_prefix=["!", "\uff01"], intents=intents)
