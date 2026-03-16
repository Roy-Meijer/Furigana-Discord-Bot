import json
from pathlib import Path

from bot import log


class FuriganaStore:
    """Persistent in-memory store mapping Discord message IDs to furigana items."""

    def __init__(self, path: Path):
        self._path = path
        self._data: dict[int, list] = {}

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = {int(k): v for k, v in json.load(f).items()}
            log.info("Loaded %d stored furigana items", len(self._data))
        except FileNotFoundError:
            self._data = {}

    def save(self):
        # keep only the latest 100000 entries to prevent unbounded growth
        if len(self._data) > 100000:
            keys = sorted(self._data)
            for k in keys[:-100000]:
                del self._data[k]
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self._data.items()}, f, ensure_ascii=False)

    def get(self, message_id: int):
        return self._data.get(message_id)

    def put(self, message_id: int, items):
        self._data[message_id] = items
        self.save()
