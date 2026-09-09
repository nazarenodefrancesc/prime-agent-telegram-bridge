from pathlib import Path

from prime_telegram_bridge.transcript_recovery import (
    build_recovery_capsule,
    parse_transcript,
)


def test_parse_known_prime_messages_and_ignore_tools_reasoning(tmp_path: Path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"type":"session","id":"root"}\n'
        '{"type":"message","id":"u1","message":{"role":"user","content":"ippopotamo"}}\n'
        '{"type":"message","id":"tool","message":{"role":"tool","content":"secret"}}\n'
        '{"type":"message","id":"a1","message":{"role":"assistant","content":[{"type":"text","text":"ricevuto"},{"type":"thinking","text":"private"}]}}\n',
        encoding="utf-8",
    )

    result = parse_transcript(path)

    assert [(turn.role, turn.text) for turn in result.turns] == [
        ("user", "ippopotamo"),
        ("assistant", "ricevuto"),
    ]
    assert result.confidence == "high"


def test_parser_tolerates_future_envelope_duplicates_and_corrupt_tail(tmp_path: Path):
    path = tmp_path / "future.jsonl"
    path.write_text(
        '{"payload":{"message":{"role":"user","content":[{"type":"text","value":"ciao"}]}},"extra":true}\n'
        '{"message":{"role":"user","content":"ciao"}}\n'
        '{"message":{"role":"assistant","content":"mondo"}}\n'
        '{"message":{"role":"assistant","content":"mondo"}}\n'
        '{"message":{"role":"system","content":"ignore"}}\n'
        '{"message":\n',
        encoding="utf-8",
    )

    result = parse_transcript(path)

    assert [(turn.role, turn.text) for turn in result.turns] == [("user", "ciao"), ("assistant", "mondo")]
    assert result.invalid_records == 1
    assert result.adapter == "semantic-role-content"


def test_capsule_is_bounded_and_labels_history_as_data():
    source = "\n".join(
        [
            '{"message":{"role":"user","content":"uno"}}',
            '{"message":{"role":"assistant","content":"due"}}',
        ]
    )
    # The parser contract is file based; this test is intentionally small and deterministic.
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        transcript = Path(directory) / "session.jsonl"
        transcript.write_text(source, encoding="utf-8")
        result = parse_transcript(transcript)
        capsule = build_recovery_capsule(result, max_turns=20, max_chars=600)

    assert capsule.startswith(
        "[Conversation recovery context]\n\n"
        "Prime session recovery: The previous Prime runtime could not be restored, "
        "but its conversation history was recovered into a new session. "
        "Runtime-only state was not recovered.\n\n"
    )
    assert "historical conversation context" in capsule
    assert "USER:\nuno" in capsule
    assert "ASSISTANT:\ndue" in capsule
    assert len(capsule) <= 600
