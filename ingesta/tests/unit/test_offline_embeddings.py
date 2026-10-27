import pytest

from ingest.offline_embeddings import DIGEST, MODEL, OllamaBatchEmbeddings, validate_vector


@pytest.mark.parametrize(
    "vector", [[1.0], [float("nan")] * 768, [float("inf")] * 768, [True] * 768]
)
def test_invalid_vectors_rejected(vector):
    with pytest.raises(ValueError):
        validate_vector(vector)


def test_batch_cache_and_manifest(monkeypatch, tmp_path):
    calls = []

    def request(self, path, body=None):
        calls.append((path, body))
        if path == "/api/tags":
            return {"models": [{"name": MODEL, "digest": DIGEST}]}
        assert path == "/api/embed" and body["truncate"] is False
        return {"embeddings": [[0.1] * 768 for _ in body["input"]]}

    monkeypatch.setattr(OllamaBatchEmbeddings, "_request", request)
    client = OllamaBatchEmbeddings(tmp_path / "cache.sqlite")
    assert len(client.embed(["a", "b", "a"])) == 3
    client.embed(["a", "b"])
    assert len([c for c in calls if c[0] == "/api/embed"]) == 1
    assert client.manifest()["new_embeddings"] == 2
    assert client.manifest()["llm_api_calls"] == 0
    assert len(client.manifest()["cache_checksum"]) == 64
    client.close()


def test_wrong_digest_fails_before_embedding(monkeypatch, tmp_path):
    monkeypatch.setattr(OllamaBatchEmbeddings, "_request", lambda *a: {"models": []})
    with pytest.raises(ValueError, match="digest"):
        OllamaBatchEmbeddings(tmp_path / "cache.sqlite")
