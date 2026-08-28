from prime_telegram_bridge.telegram_api import parse_update, split_telegram_text


def test_split_telegram_text_preserves_content():
    text = ("line one\n" * 1000).strip()
    chunks = split_telegram_text(text, limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "".join(chunks).replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")


def test_parse_photo_message_uses_largest_photo():
    msg = parse_update(
        {
            "update_id": 7,
            "message": {
                "message_id": 8,
                "chat": {"id": 10},
                "from": {"id": 11},
                "caption": "hello",
                "photo": [{"file_id": "small"}, {"file_id": "large"}],
            },
        }
    )
    assert msg is not None
    assert msg.photo_file_id == "large"
    assert msg.text == "hello"
