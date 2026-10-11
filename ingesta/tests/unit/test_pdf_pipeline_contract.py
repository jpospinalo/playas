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


@pytest.fixture
def g3_local_pipeline(tmp_path, monkeypatch):
    import socket

    import boto3
    from PIL import Image

    forbidden = Mock(side_effect=AssertionError("External access or real converter prohibited"))
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3.session.Session, "client", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)

    from ingest import s3_client
    from ingest.pdf_to_md import pipeline

    monkeypatch.setattr(s3_client, "_get_client", forbidden)
    for name in (
        "list_keys",
        "download_file",
        "upload_file",
        "upload_directory",
        "DocumentConverter",
        "_build_converter",
    ):
        monkeypatch.setattr(pipeline, name, forbidden)

    root = tmp_path.resolve()
    state = SimpleNamespace(
        pipeline=pipeline,
        root=root,
        output_dir=root / "salida",
        pdf_path=root / "entrada" / "documento.pdf",
        image_name="figura.png",
        alt="a",
        caption="Mapa",
        preamble=False,
        angled=False,
        size=500,
        tail="\n\n## Consideraciones\nFigura de prueba para el expediente. DIMAR regula playas.\n",
        spies={},
    )
    for name in (
        "relativize_image_refs",
        "profile_legal_document",
        "adaptive_cleanup",
        "evaluate_document_quality",
    ):
        spy = Mock(wraps=getattr(pipeline, name))
        state.spies[name] = spy
        monkeypatch.setattr(pipeline, name, spy)
    monkeypatch.setattr(pipeline, "time", SimpleNamespace(time=Mock(side_effect=[10.0, 12.0])))

    def export(md_path, *, artifacts_dir, image_mode):
        assert md_path == (state.output_dir / f"{state.pdf_path.stem}.md").resolve()
        assert (
            artifacts_dir.resolve() == (state.output_dir / state.pdf_path.stem / "assets").resolve()
        )
        assert image_mode == pipeline.ImageRefMode.REFERENCED
        assert md_path.is_relative_to(root)
        assert artifacts_dir.resolve().is_relative_to(root)
        line = ""
        if state.image_name is not None:
            assert len(state.pdf_path.stem.encode("utf-8")) < 200
            assert len(state.image_name.encode("utf-8")) < 200
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            state.asset = (artifacts_dir / state.image_name).resolve()
            assert state.asset.is_relative_to(root)
            area = state.size * state.size
            pixels = (bytes(range(256)) * ((area + 255) // 256))[:area]
            with Image.frombytes("L", (state.size, state.size), pixels) as image:
                image.save(state.asset)
            state.image_bytes = state.asset.read_bytes()
            raw = f"<{state.asset}>" if state.angled else str(state.asset)
            state.raw_token = f"![{state.alt}]({raw})"
            line = f"{state.caption} {state.raw_token}".strip()
        state.exported = ("" if state.preamble else "## Inicio\n\n") + line + state.tail
        md_path.write_text(state.exported, encoding="utf-8")

    state.exporter = Mock(side_effect=export)
    state.converter = SimpleNamespace(
        convert=Mock(
            return_value=SimpleNamespace(document=SimpleNamespace(save_as_markdown=state.exporter))
        )
    )
    yield state
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    ("stem", "image_name", "alt", "caption", "preamble", "angled"),
    [
        ("documento_ascii", "figura.png", "Image14", "Figura del expediente", False, False),
        ("Documento legal", "a b.png", "", "Mapa", True, False),
        ("Sentencia costera", "á é.png", "a", "Fig. 1", False, True),
        ("documento_nfd", "Cafe\u0301.png", "a", "", True, False),
        ("documento_parentesis", "foto((anexo)).png", "Image14", "Mapa", False, False),
        ("documento_porcentaje", "a%20b.png", "a", "Mapa", True, False),
        ("documento_raw", "a%literal b.png", "a", "Fig. 1", False, False),
        (
            "Documento" + "a" * 39 + " de (anexo)",
            "image_" + "1234567890" * 6 + "ab87.png",
            "",
            "Mapa",
            True,
            False,
        ),
    ],
    ids=[
        "ascii",
        "space",
        "unicode-delimited",
        "nfd-standalone",
        "nested-parentheses",
        "literal-escape",
        "raw-percent",
        "long-mixed",
    ],
)
def test_g3_real_pipeline_persists_images_and_sidecars(
    g3_local_pipeline, stem, image_name, alt, caption, preamble, angled
):
    import math
    from dataclasses import asdict
    from urllib.parse import quote, unquote

    from ingest.pdf_to_md.images import _resolve_image_path, relativize_image_refs
    from ingest.pdf_to_md.models import DocumentQualityReport

    state = g3_local_pipeline
    state.pdf_path = state.root / "entrada" / f"{stem}.pdf"
    state.image_name, state.alt, state.caption = image_name, alt, caption
    state.preamble, state.angled = preamble, angled
    md_path, report = state.pipeline._run_pipeline(
        state.pdf_path, state.output_dir, state.converter
    )

    destination = quote(f"./{stem}/assets/{image_name}", safe="/._-~")
    token = f"![{alt}]({destination})"
    serialized = state.exported.replace(state.raw_token, token)
    state.converter.convert.assert_called_once_with(state.pdf_path)
    state.exporter.assert_called_once_with(
        md_path,
        artifacts_dir=state.output_dir / stem / "assets",
        image_mode=state.pipeline.ImageRefMode.REFERENCED,
    )
    for spy in state.spies.values():
        assert spy.call_count == 1
    state.spies["relativize_image_refs"].assert_called_once_with(state.exported, md_path)
    state.spies["profile_legal_document"].assert_called_once_with(serialized)
    cleanup_args = state.spies["adaptive_cleanup"].call_args.args
    quality_args = state.spies["evaluate_document_quality"].call_args.args
    assert cleanup_args[0] == quality_args[0] == serialized
    assert cleanup_args[2] == md_path
    assert cleanup_args[1] is quality_args[4]

    persisted = md_path.read_text(encoding="utf-8")
    assert persisted == quality_args[1]
    assert token in persisted
    assert caption in persisted
    assert "Figura de prueba para el expediente." in persisted
    assert str(state.asset) not in persisted
    assert unquote(destination) == f"./{stem}/assets/{image_name}"
    assert _resolve_image_path(destination, md_path.parent) == state.asset
    assert state.asset.read_bytes() == state.image_bytes
    assert relativize_image_refs(persisted, md_path) == persisted
    assert isinstance(report, DocumentQualityReport)
    assert report.processing_time_seconds == 2.0
    report_dict = asdict(report)
    assert all(math.isfinite(v) for v in report_dict.values() if isinstance(v, (int, float)))
    doc_dir = state.output_dir / stem
    assert json.loads((doc_dir / f"{stem}.quality.json").read_text()) == report_dict
    assert quality_args[3]
    assert json.loads((doc_dir / f"{stem}.entities.json").read_text()) == quality_args[3]
    assert md_path.is_relative_to(state.root)
    assert all(path.resolve().is_relative_to(state.root) for path in state.output_dir.rglob("*"))


def test_g3_text_without_images_or_entities_has_no_entity_sidecar(g3_local_pipeline):
    from dataclasses import asdict

    state = g3_local_pipeline
    state.image_name = None
    state.tail = "\n\n## Consideraciones\nTexto de prueba para el expediente.\n"
    md_path, report = state.pipeline._run_pipeline(
        state.pdf_path, state.output_dir, state.converter
    )
    quality_args = state.spies["evaluate_document_quality"].call_args.args
    assert quality_args[3] == {}
    assert md_path.read_text(encoding="utf-8") == quality_args[1]
    assert "Texto de prueba para el expediente." in quality_args[1]
    doc_dir = state.output_dir / state.pdf_path.stem
    assert json.loads((doc_dir / f"{state.pdf_path.stem}.quality.json").read_text()) == asdict(
        report
    )
    assert not (doc_dir / f"{state.pdf_path.stem}.entities.json").exists()
    assert len(list(state.output_dir.rglob("*.json"))) == 1
    state.converter.convert.assert_called_once_with(state.pdf_path)
    assert state.exporter.call_count == 1


def test_g3_real_filter_removes_only_the_small_temporary_image(g3_local_pipeline):
    from dataclasses import asdict
    from urllib.parse import quote

    state = g3_local_pipeline
    state.size = 32
    md_path, report = state.pipeline._run_pipeline(
        state.pdf_path, state.output_dir, state.converter
    )
    destination = quote(f"./{state.pdf_path.stem}/assets/{state.image_name}", safe="/._-~")
    token = f"![{state.alt}]({destination})"
    assert token in state.spies["adaptive_cleanup"].call_args.args[0]
    assert not state.asset.exists()
    persisted = md_path.read_text(encoding="utf-8")
    assert token not in persisted
    assert "Figura de prueba para el expediente." in persisted
    assert persisted == state.spies["evaluate_document_quality"].call_args.args[1]
    doc_dir = state.output_dir / state.pdf_path.stem
    assert json.loads((doc_dir / f"{state.pdf_path.stem}.quality.json").read_text()) == asdict(
        report
    )
    state.converter.convert.assert_called_once_with(state.pdf_path)
    assert state.exporter.call_count == 1


def test_g3_conversion_error_propagates_without_outputs(g3_local_pipeline):
    state = g3_local_pipeline
    state.converter.convert.side_effect = RuntimeError("synthetic conversion failure")
    with pytest.raises(RuntimeError, match="synthetic conversion failure"):
        state.pipeline._run_pipeline(state.pdf_path, state.output_dir, state.converter)
    state.converter.convert.assert_called_once_with(state.pdf_path)
    state.exporter.assert_not_called()
    for spy in state.spies.values():
        spy.assert_not_called()
    assert not state.output_dir.exists()
