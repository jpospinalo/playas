"""Contratos de orquestación con archivos sintéticos, sin OCR, modelos ni AWS."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def pdf_batch(monkeypatch):
    from ingest import s3_client
    from ingest.pdf_to_md import pipeline
    from ingest.pdf_to_md.models import DocumentQualityReport

    # Cualquier acceso accidental al cliente real debe fallar, no contactar AWS.
    monkeypatch.setattr(s3_client, "_get_client", Mock(side_effect=AssertionError("AWS prohibido")))
    state = SimpleNamespace(
        pipeline=pipeline,
        keys=[],
        objects={},
        sources={},
        contents={},
        without_assets=set(),
        processing_errors=set(),
        downloaded=[],
        processed=[],
        directories=[],
        quality=DocumentQualityReport(final_quality=90),
        converter=object(),
    )

    def download(key, local_path):
        state.downloaded.append(key)
        state.sources[local_path] = key
        Path(local_path).write_bytes(b"synthetic PDF; never parsed")

    def process(pdf_path, output_dir, converter):
        assert converter is state.converter
        key = state.sources[str(pdf_path)]
        state.processed.append((key, pdf_path, output_dir))
        if key in state.processing_errors:
            raise RuntimeError("synthetic processing failure")
        stem = pdf_path.stem
        doc_dir = output_dir / stem
        doc_dir.mkdir(exist_ok=True)
        md_path = output_dir / f"{stem}.md"
        content = state.contents.get(key, "Texto sintético.\n")
        if key not in state.without_assets:
            assets = doc_dir / "assets"
            assets.mkdir(exist_ok=True)
            (assets / "figura.png").write_bytes(key.encode())
            (doc_dir / f"{stem}.entities.json").write_text(json.dumps({"source": key}))
            content += f"![Figura](<{stem}/assets/figura.png>)\n"
        (doc_dir / f"{stem}.quality.json").write_text('{"final_quality": 90}')
        md_path.write_text(content, encoding="utf-8")
        return md_path, state.quality

    def upload(local_path, key):
        state.objects[key] = Path(local_path).read_bytes()

    def upload_dir(local_dir, prefix):
        state.directories.append(prefix)
        local_root = Path(local_dir)
        for path in local_root.rglob("*"):
            if path.is_file():
                upload(str(path), prefix + path.relative_to(local_root).as_posix())

    state.listing = Mock(side_effect=lambda prefix, suffix: list(state.keys))
    state.builder = Mock(return_value=state.converter)
    monkeypatch.setattr(pipeline, "list_keys", state.listing)
    monkeypatch.setattr(pipeline, "_build_converter", state.builder)
    monkeypatch.setattr(pipeline, "download_file", download)
    monkeypatch.setattr(pipeline, "_run_pipeline", process)
    monkeypatch.setattr(pipeline, "upload_file", upload)
    monkeypatch.setattr(pipeline, "upload_directory", upload_dir)
    return state


@pytest.mark.parametrize(
    ("key", "prefix"),
    [
        ("data/raw/jurisprudencia/fallo.pdf", "data/bronze/jurisprudencia/"),
        ("data/raw/normativa/decreto.pdf", "data/bronze/normativa/"),
        ("data/raw/normativa/subcarpeta/decreto.pdf", "data/bronze/normativa/"),
        ("data/raw/jurisprudencia/Sentencia marítima 1.pdf", "data/bronze/jurisprudencia/"),
    ],
)
def test_typed_batch_preserves_prefix_and_relative_artifacts(pdf_batch, key, prefix):
    pdf_batch.keys = [key]
    stem = Path(key).stem
    expected = f"{prefix}{stem}.md"

    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [expected]
    assert pdf_batch.objects[expected].decode() == (
        f"Texto sintético.\n![Figura](<{stem}/assets/figura.png>)\n"
    )
    assert pdf_batch.objects[f"{prefix}{stem}/assets/figura.png"] == key.encode()
    assert f"{prefix}{stem}/{stem}.quality.json" in pdf_batch.objects
    assert f"{prefix}{stem}/{stem}.entities.json" in pdf_batch.objects
    assert pdf_batch.directories == [f"{prefix}{stem}/"]
    pdf_batch.builder.assert_called_once_with()
    pdf_batch.listing.assert_called_once_with("data/raw/", suffix=".pdf")


@pytest.mark.parametrize(
    "key",
    [
        "data/raw/archivo.pdf",
        "data/raw/historico/subcarpeta/fallo.pdf",
        "data/raw/normativa_archivo.pdf",
        "data/raw/historico/normativa/fallo.pdf",
        "data/raw/Normativa/decreto.pdf",
    ],
)
def test_legacy_batch_preserves_flat_output_without_inference(pdf_batch, key):
    pdf_batch.keys = [key]
    stem = Path(key).stem
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [f"data/bronze/{stem}.md"]
    assert pdf_batch.directories == [f"data/bronze/{stem}/"]


def test_legacy_batch_warns_about_loader_exclusion(pdf_batch, caplog):
    pdf_batch.keys = ["data/raw/historico/fallo.pdf"]
    with caplog.at_level(logging.WARNING):
        pdf_batch.pipeline.convert_pdfs_to_markdown()
    assert "data/raw/historico/fallo.pdf" in caplog.text
    assert "loaders" in caplog.text


@pytest.mark.parametrize(
    "keys",
    [
        ["data/raw/normativa/a/decreto.pdf", "data/raw/normativa/b/decreto.pdf"],
        ["data/raw/fallo.pdf", "data/raw/historico/fallo.pdf"],
        ["data/raw/historico/fallo.pdf", "data/raw/otra/fallo.pdf"],
        [
            "data/raw/valido.pdf",
            "data/raw/normativa/a/decreto.pdf",
            "data/raw/normativa/b/decreto.pdf",
        ],
    ],
)
def test_collision_fails_before_converter_or_document_io(pdf_batch, keys):
    pdf_batch.keys = keys
    with pytest.raises(ValueError) as error:
        pdf_batch.pipeline.convert_pdfs_to_markdown()
    assert all(key in str(error.value) for key in keys[-2:])
    pdf_batch.builder.assert_not_called()
    assert pdf_batch.downloaded == []
    assert pdf_batch.processed == []
    assert pdf_batch.objects == {}


def test_same_stem_distinct_destinations_do_not_mix_assets(pdf_batch):
    first = "data/raw/jurisprudencia/igual.pdf"
    second = "data/raw/normativa/igual.pdf"
    pdf_batch.keys = [first, second]
    pdf_batch.without_assets.add(second)
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [
        "data/bronze/jurisprudencia/igual.md",
        "data/bronze/normativa/igual.md",
    ]
    assert "data/bronze/jurisprudencia/igual/assets/figura.png" in pdf_batch.objects
    assert "data/bronze/normativa/igual/assets/figura.png" not in pdf_batch.objects
    assert "data/bronze/normativa/igual/igual.entities.json" not in pdf_batch.objects
    assert "data/bronze/normativa/igual/igual.quality.json" in pdf_batch.objects
    assert pdf_batch.objects["data/bronze/normativa/igual.md"] == b"Texto sint\xc3\xa9tico.\n"
    assert len({out for _, _, out in pdf_batch.processed}) == 2
    assert len({pdf.parent for _, pdf, _ in pdf_batch.processed}) == 2
    assert all(not out.exists() and not pdf.exists() for _, pdf, out in pdf_batch.processed)
    pdf_batch.builder.assert_called_once_with()


def test_legacy_and_typed_same_stem_have_distinct_destinations(pdf_batch):
    pdf_batch.keys = ["data/raw/igual.pdf", "data/raw/normativa/igual.pdf"]
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [
        "data/bronze/igual.md",
        "data/bronze/normativa/igual.md",
    ]
    assert pdf_batch.directories == ["data/bronze/igual/", "data/bronze/normativa/igual/"]
    pdf_batch.builder.assert_called_once_with()


def test_repeated_source_key_is_not_a_collision(pdf_batch):
    key = "data/raw/archivo.pdf"
    pdf_batch.keys = [key, key]
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == ["data/bronze/archivo.md"] * 2
    assert pdf_batch.downloaded == [key, key]
    pdf_batch.builder.assert_called_once_with()


def test_batch_isolates_temporary_paths_without_rebuilding_converter(pdf_batch):
    pdf_batch.keys = ["data/raw/primero.pdf", "data/raw/segundo.pdf"]
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [
        "data/bronze/primero.md",
        "data/bronze/segundo.md",
    ]
    assert len({out for _, _, out in pdf_batch.processed}) == 2
    assert len({pdf.parent for _, pdf, _ in pdf_batch.processed}) == 2
    pdf_batch.builder.assert_called_once_with()


def test_empty_batch_does_not_build_converter(pdf_batch):
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == []
    pdf_batch.builder.assert_not_called()
    assert pdf_batch.objects == {}


def test_processing_failure_continues_in_original_order(pdf_batch):
    keys = [f"data/raw/{name}.pdf" for name in ("primero", "fallido", "ultimo")]
    pdf_batch.keys = keys
    pdf_batch.processing_errors.add(keys[1])
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == [
        "data/bronze/primero.md",
        "data/bronze/ultimo.md",
    ]
    assert pdf_batch.downloaded == keys
    assert [key for key, _, _ in pdf_batch.processed] == keys
    assert all(not out.exists() and not pdf.exists() for _, pdf, out in pdf_batch.processed)


def test_batch_download_failure_still_propagates(pdf_batch, monkeypatch):
    pdf_batch.keys = ["data/raw/archivo.pdf"]
    monkeypatch.setattr(
        pdf_batch.pipeline, "download_file", Mock(side_effect=RuntimeError("download failure"))
    )
    with pytest.raises(RuntimeError, match="download failure"):
        pdf_batch.pipeline.convert_pdfs_to_markdown()
    assert pdf_batch.processed == []
    assert pdf_batch.objects == {}


@pytest.mark.parametrize("upload_function", ["upload_file", "upload_directory"])
def test_batch_upload_failure_preserves_continuation(pdf_batch, monkeypatch, upload_function):
    pdf_batch.keys = ["data/raw/fallido.pdf", "data/raw/ultimo.pdf"]
    original = getattr(pdf_batch.pipeline, upload_function)

    def upload(local_path, destination):
        if "fallido" in destination:
            raise RuntimeError("synthetic upload failure")
        return original(local_path, destination)

    monkeypatch.setattr(pdf_batch.pipeline, upload_function, upload)
    assert pdf_batch.pipeline.convert_pdfs_to_markdown() == ["data/bronze/ultimo.md"]
    assert pdf_batch.downloaded == pdf_batch.keys


_OMITTED = object()


@pytest.mark.parametrize("key", ["data/raw/normativa/decreto.pdf", "data/raw/decreto.pdf"])
@pytest.mark.parametrize("prefix", [_OMITTED, None, "", "custom/", "literal-no-slash"])
def test_single_pdf_preserves_public_default_and_literal_prefix(pdf_batch, key, prefix):
    if prefix is _OMITTED:
        result = pdf_batch.pipeline.process_single_pdf(key)
    else:
        result = pdf_batch.pipeline.process_single_pdf(key, output_prefix=prefix)
    expected_prefix = "data/bronze/" if prefix is _OMITTED else prefix or "data/bronze/"
    assert result == (f"{expected_prefix}decreto.md", pdf_batch.quality)
    assert pdf_batch.directories == [f"{expected_prefix}decreto/"]
    assert pdf_batch.objects[f"{expected_prefix}decreto/assets/figura.png"] == key.encode()
    assert pdf_batch.objects[f"{expected_prefix}decreto.md"].decode() == (
        "Texto sintético.\n![Figura](<decreto/assets/figura.png>)\n"
    )
    pdf_batch.builder.assert_called_once_with()


def test_single_pdf_processing_failure_preserves_none(pdf_batch):
    key = "data/raw/normativa/decreto.pdf"
    pdf_batch.processing_errors.add(key)
    assert pdf_batch.pipeline.process_single_pdf(key) is None
    assert pdf_batch.objects == {}


@pytest.mark.parametrize("upload_function", ["upload_file", "upload_directory"])
def test_single_pdf_upload_failure_preserves_none(pdf_batch, monkeypatch, upload_function):
    monkeypatch.setattr(
        pdf_batch.pipeline, upload_function, Mock(side_effect=RuntimeError("upload failure"))
    )
    assert pdf_batch.pipeline.process_single_pdf("data/raw/normativa/decreto.pdf") is None


def test_single_pdf_download_failure_still_propagates(pdf_batch, monkeypatch):
    monkeypatch.setattr(
        pdf_batch.pipeline, "download_file", Mock(side_effect=RuntimeError("download failure"))
    )
    with pytest.raises(RuntimeError, match="download failure"):
        pdf_batch.pipeline.process_single_pdf("data/raw/normativa/decreto.pdf")
    assert pdf_batch.processed == []
    assert pdf_batch.objects == {}


@pytest.mark.parametrize("doc_type", ["jurisprudencia", "normativa"])
def test_conversion_feeds_real_loader_with_metadata_and_silver_output(
    pdf_batch, monkeypatch, doc_type
):
    from ingest import loaders, utils

    key = f"data/raw/{doc_type}/documento_legal.pdf"
    other_key = "data/raw/legado.pdf"
    pdf_batch.keys = [key, other_key]
    pdf_batch.without_assets.update(pdf_batch.keys)
    text = (
        "## Antecedentes\nHechos.\n## Consideraciones\nAnálisis.\n## Falla\nDecisión."
        if doc_type == "jurisprudencia"
        else "DECRETA\nArtículo 1. Objeto.\nRegla sintética sobre playas."
    )
    pdf_batch.contents[key] = text
    pdf_batch.pipeline.convert_pdfs_to_markdown()

    listing = Mock(
        side_effect=lambda prefix, suffix: [
            k for k in pdf_batch.objects if k.startswith(prefix) and k.endswith(suffix)
        ]
    )
    monkeypatch.setattr(loaders, "list_keys", listing)
    monkeypatch.setattr(loaders, "read_text", lambda k: pdf_batch.objects[k].decode())
    monkeypatch.setattr(loaders, "load_metadata_csv", lambda _: {})
    monkeypatch.setattr(loaders, "get_metadata_for_file", lambda *_: {})
    # Ejecutar también la persistencia JSONL real; sustituir solo su I/O remoto.
    monkeypatch.setattr(
        utils, "write_text", lambda k, value: pdf_batch.objects.update({k: value.encode()})
    )

    sections = loaders._load_doc_type(doc_type)
    assert sections
    assert any(section.page_content for section in sections)
    assert all(section.metadata["doc_type"] == doc_type for section in sections)
    assert all(section.metadata["source"] == "documento_legal.md" for section in sections)
    assert all(section.metadata["title"] == "documento legal" for section in sections)
    listing.assert_called_once_with(f"data/bronze/{doc_type}/", suffix=".md")
    rows = [
        json.loads(line)
        for line in pdf_batch.objects[f"data/silver/{doc_type}/documento_legal.jsonl"]
        .decode()
        .splitlines()
    ]
    assert rows == [{"page_content": s.page_content, "metadata": s.metadata} for s in sections]
