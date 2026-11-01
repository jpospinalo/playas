"""Regresiones del filtro sobre imágenes sintéticas dentro de tmp_path."""

import pytest
from PIL import Image

from ingest.pdf_to_md import images


def _write_image(path, width, height, uniform=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    size = width * height
    pixels = bytes(size) if uniform else (bytes(range(256)) * ((size + 255) // 256))[:size]
    with Image.frombytes("L", (width, height), pixels) as image:
        image.save(path)
    return path.read_bytes()


@pytest.mark.parametrize(
    ("width", "height", "uniform", "context", "keep"),
    [
        (32, 32, False, "Figura de prueba.", False),
        (400, 400, False, "Figura de prueba.", True),
        (400, 400, False, "Texto de prueba.", False),
        (512, 512, True, "Figura de prueba.", False),
        (500, 500, False, "Texto de prueba.", True),
    ],
)
def test_size_variance_and_context_preserve_markdown_and_files(
    tmp_path, monkeypatch, width, height, uniform, context, keep
):
    monkeypatch.setattr(images, "IMAGE_FALLBACK_KEEP_ENABLED", False)
    path = tmp_path / "assets" / "sample.png"
    original_bytes = _write_image(path, width, height, uniform)
    token = "![asset](assets/sample.png)"
    markdown = f"{context}\n{token}\n"

    result = images.filter_images(markdown, tmp_path / "document.md")

    assert result == (markdown if keep else markdown.replace(token, ""))
    assert path.exists() is keep
    if keep:
        assert path.read_bytes() == original_bytes


def test_duplicate_hash_removes_only_second_file_and_reference(tmp_path):
    first = tmp_path / "assets" / "first.png"
    second = tmp_path / "assets" / "second.png"
    original_bytes = _write_image(first, 400, 400)
    second.write_bytes(original_bytes)
    markdown = "Figura de prueba.\n![a](assets/first.png)\n![b](assets/second.png)\n"

    assert images.filter_images(markdown, tmp_path / "document.md") == markdown.replace(
        "![b](assets/second.png)", ""
    )
    assert first.read_bytes() == original_bytes
    assert not second.exists()


@pytest.mark.parametrize(
    ("sizes", "expected"),
    [
        ([(600, 600), (500, 500), (400, 400), (32, 32)], {0, 1}),
        ([(399, 400), (400, 400), (350, 350)], {1}),
    ],
)
def test_fallback_keeps_largest_images_with_original_area_threshold(tmp_path, sizes, expected):
    tokens = []
    originals = {}
    for index, (width, height) in enumerate(sizes):
        path = tmp_path / "assets" / f"{index}.png"
        originals[index] = _write_image(path, width, height, uniform=True)
        tokens.append(f"![asset](assets/{index}.png)")
    markdown = "Texto de prueba.\n" + "\n".join(tokens)

    result = images.filter_images(markdown, tmp_path / "document.md")

    expected_markdown = markdown
    for index, token in enumerate(tokens):
        path = tmp_path / "assets" / f"{index}.png"
        if index in expected:
            assert path.read_bytes() == originals[index]
        else:
            assert not path.exists()
            expected_markdown = expected_markdown.replace(token, "")
    assert result == expected_markdown


def test_absent_image_reference_is_preserved(tmp_path):
    markdown = "Texto.\n![asset](assets/missing.png)\n"
    assert images.filter_images(markdown, tmp_path / "document.md") == markdown
    assert list(tmp_path.iterdir()) == []
