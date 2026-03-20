# tests/unit/test_vectorstore.py
from src.backend.vectorstore import sanitize_metadata


def test_sanitize_metadata_preserves_primitives():
    meta = {"key_str": "value", "key_int": 42, "key_float": 3.14, "key_bool": True}
    result = sanitize_metadata(meta)
    assert result == meta


def test_sanitize_metadata_converts_lists():
    meta = {"keywords": ["horror", "poe"]}
    result = sanitize_metadata(meta)
    assert isinstance(result["keywords"], str)
    assert "horror" in result["keywords"]


def test_sanitize_metadata_converts_dicts():
    meta = {"nested": {"a": 1}}
    result = sanitize_metadata(meta)
    assert isinstance(result["nested"], str)
