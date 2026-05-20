# Furigana Bot

A Discord bot which adds inline furigana to Japanese kanji words and provides kanji reading lists. Supports text input, image input and slash commands.

---

## Project structure

```
furigana-bot-development/
├── main.py                     # Entry point
├── bot_token.txt               # Bot token (not in repository)
├── allowed_users.txt           # List of roles and users which can add or remove emoji mappings (not in repository)
├── allowed_users.example.txt   # Template for allowed_users.txt
├── requirements.txt            # Python requirements
├── bot/
│   ├── __init__.py             # Shared instances
│   ├── commands.py             # All commands and events
│   ├── converters.py           # Furigana / kanji list logic
│   ├── store.py                # Make buttons persistent accros restarts of the bot
│   ├── views.py                # Persistent Discord UI buttons
│   └── image_text.py           # Helper functions for extracting text from images
└── data/
    ├── kanji_emoji.json        # Kanji to emoji mappings
    └── furigana_store.json     # Message history, makes the buttons survive bot restart (not in repository, automatically generated)
```

---

## Features
- Generates inline furigana or kanji lists from Japanese text or an image.  
- Kanji list also tries to map an emoji for comprehensibility
- **Prefix commands:**
  - **`!furi`** — Generate furigana for text only (ignores image attachments)
  - **`!furiimage`** / **`!furiimg`** — Generate furigana for images only (OCR)
  - **`!furiall`** — Generate furigana for both text and images
  - Reply with any command to process quoted message
- **Slash command:** **`/furi`** — Generate furigana with text/image options
- **Context menu (right-click a message):**
  - **ふりがな テキスト / Get Furigana Text** — text only
  - **ふりがな 画像 / Get Furigana Image** — images only
  - **ふりがな / Get Furigana** — both text and images
- **`/emoji_add`** — Add or update a kanji to emoji mapping (privileged)
  - Existing mappings are shown as autocomplete suggestions while typing
- **`/emoji_remove`** — Remove an emoji mapping (privileged)
  - Existing mappings are shown as autocomplete suggestions while typing
- Inline furigana format: `漢字||(かんじ)||`
- Kanji list format: `漢字 = かんじ 📖`
- Also works with ！(full-width) and aliases: `!furigana` `!ふりがな` `!フリガナ`

---

## Running the bot

```shell
python main.py
```

The bot token is read from `bot_token.txt` in the project root.

---

## Access control

`allowed_users.txt` controls who may use `/emoji_add` and `/emoji_remove`. This file is **not** committed to the repository (it's gitignored) to keep user and role IDs private.

Copy the example file to get started:

```shell
cp allowed_users.example.txt allowed_users.txt
```

Then edit it to add your roles and users:

```
# Grant access to a specific user
user:123456789012345678

# Grant access to everyone with a role
role:987654321098765432
```

Add entries and restart the bot.

---

## Set up Python virtual environment

Useful so that everyone involved in the project can use the same Python version and packages (and other Python versions/packages in other projects).

1. Install [pyenv](https://github.com/pyenv/pyenv) with this command:

```shell
curl https://pyenv.run | bash
```

2. Add some lines to `~/.bashrc` with these commands:

```shell
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
```

3. Restart your shell with this command:

```shell
exec "$SHELL"
```

4. Run the following command to install packages required for pyenv:

```shell
sudo apt-get -y install build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev tk-dev
```

5. Create a Python virtual environment ([pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv)) with the following commands:

```shell
pyenv install 3.10.12
pyenv virtualenv 3.10.12 furigana-bot-3.10.12
```

6. Navigate to the project directory and run the following command to assign the Python virtual environment for this project:

```shell
pyenv local furigana-bot-3.10.12
```

7. Run this command:

```shell
python --version
```

The output should show `Python 3.10.12`.

8. Navigate to the project directory again and install the packages used in the project with this command:

```shell
pip install -r requirements.txt
```

When installing new packages, you can update the requirements file with this command:

```shell
pip freeze > requirements.txt
```

The Python virtual environment should now be activated automatically when navigating to the project directory (or a subdirectory), and deactivated when navigating outside the project directory. It can also be used in Jupyter notebooks by opening a notebook, clicking on the Python version in the top right, and selecting `furigana-bot-3.10.12 (Python 3.10.12) ~./pyenv/versions/furigana-bot-3.10.12/bin/python`.