"""
Test the furigana bot logic locally without Discord.
Run: python test_local.py
"""
from bot import converter
from bot.converters import _RE_KANJI


def simulate_furi_command(sentence=None, message_content="", attachments_texts=None,
                          quoted_content=None, quoted_attachments_texts=None):
    """
    Simulates the !furi command logic.
    - sentence: text passed after !furi (e.g. "!furi 日本語")
    - message_content: the raw message content
    - attachments_texts: dict of {filename: ocr_text} for original message attachments
    - quoted_content: text of the quoted/replied message
    - quoted_attachments_texts: dict of {filename: ocr_text} for quoted message attachments
    """
    furigana_items = []

    # Step 1: Check original message text
    text_to_use = sentence if sentence else message_content
    if text_to_use and _RE_KANJI.search(text_to_use):
        furigana_items.append(("メッセージ", text_to_use))

    # Step 2: Check original message attachments
    if attachments_texts:
        for filename, ocr_text in attachments_texts.items():
            if ocr_text and _RE_KANJI.search(ocr_text):
                furigana_items.append((f"📎 {filename}", ocr_text))

    # Step 3: Only if nothing above had kanji, check quoted message
    if not furigana_items and (quoted_content or quoted_attachments_texts):
        if quoted_content and _RE_KANJI.search(quoted_content):
            furigana_items.append(("メッセージ (引用)", quoted_content))

        if quoted_attachments_texts:
            for filename, ocr_text in quoted_attachments_texts.items():
                if ocr_text and _RE_KANJI.search(ocr_text):
                    furigana_items.append((f"📎 {filename} (引用)", ocr_text))

    return furigana_items


def print_results(furigana_items):
    if not furigana_items:
        print("  -> Geen Japanse tekst gevonden.\n")
        return

    print("  -> インライン:")
    for label, text in furigana_items:
        print(f"     **{label}**")
        print(f"     {converter.get_inline_furigana(text)}")

    print("  -> リスト:")
    for label, text in furigana_items:
        print(f"     **{label}**")
        print(f"     {converter.get_kanji_list(text)}")
    print()


# ---- Test scenarios ----

print("=== Test 1: Message with kanji ===")
items = simulate_furi_command(sentence="日本語を勉強しています")
print_results(items)

print("=== Test 2: Message with kanji + attachment with kanji ===")
items = simulate_furi_command(
    sentence="今日は天気がいい",
    attachments_texts={"photo.png": "東京は美しい都市です"}
)
print_results(items)

print("=== Test 3: No kanji in message, fallback to quoted message ===")
items = simulate_furi_command(
    message_content="!furi",
    quoted_content="昨日は雨が降りました"
)
print_results(items)

print("=== Test 4: No kanji anywhere ===")
items = simulate_furi_command(
    message_content="hello",
    quoted_content="hi there"
)
print_results(items)

print("=== Test 5: No kanji in message, quoted attachment has kanji ===")
items = simulate_furi_command(
    message_content="!furi",
    quoted_content="no kanji here",
    quoted_attachments_texts={"screenshot.jpg": "漢字のテスト"}
)
print_results(items)

print("=== Test 6: Message has kanji, quoted also has kanji (should NOT use quoted) ===")
items = simulate_furi_command(
    sentence="食べ物",
    quoted_content="飲み物"
)
print_results(items)

print("=== Test 7: One image with multiple lines of kanji (should be ONE entry) ===")
items = simulate_furi_command(
    message_content="!furi",
    attachments_texts={"pokemon.png": "この 手紙と いっしょに\n3匹の ポケモンを 届けます\n仲良く 選んでね\n還間"}
)
print_results(items)
