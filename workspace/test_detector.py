from detector import parse_bullets
import pytest

def test_parse_bullets():
    text = "1. first\n2. second"
    expected = [{"id": 1, "text": "first"}, {"id": 2, "text": "second"}]
    assert parse_bullets(text) == expected
