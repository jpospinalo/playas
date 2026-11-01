"""Inventario con corpus/export sintéticos; sin clientes, OCR ni servicios."""

import gzip
import hashlib
import json
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from utils import audit_local_corpus
from utils.audit_local_corpus import OUTPUT_NAMES, build_catalog, main, render_markdown


def _gold_row(name="caso", cid="caso_0", text="Texto sintético.", doc_type="jurisprudencia"):
    return {
        "page_content": text,
        "metadata": {
            "source": name + ".md",
            "doc_type": doc_type,
            "chunk_id": cid,
            "title": "Título observado",
            "summary": "Resumen",
            "keywords": ["playa"],
            "entities": [],
            "articulo": None,
        },
    }


def _source(root, name="caso", rows=None, doc_type="jurisprudencia", binary=b"%PDF-1.7\nsynthetic"):
    corpus = root / "data/documents"
    rows = [_gold_row(name, doc_type=doc_type)] if rows is None else rows
    for layer in ("raw", "bronze", "silver", "gold"):
        (corpus / layer / doc_type).mkdir(parents=True, exist_ok=True)
    (corpus / "raw" / doc_type / (name + ".pdf")).write_bytes(binary)
    (corpus / "bronze" / doc_type / (name + ".md")).write_text(
        "Texto sintético.\n", encoding="utf-8"
    )
    for layer in ("silver", "gold"):
        (corpus / layer / doc_type / (name + ".jsonl")).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
    return corpus


def _export(root, rows, **manifest):
    path = root / "data/snapshot.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "__manifest__": {
                        "count": len(rows),
                        "collection": "fixture",
                        "created_at": "2026-01-01T00:00:00Z",
                        "format_version": 1,
                        "chroma_host": "private-do-not-publish",
                        **manifest,
                    }
                }
            )
            + "\n"
        )
        for row in rows:
            metadata = {k: v for k, v in row["metadata"].items() if v is not None}
            if isinstance(metadata.get("keywords"), list):
                metadata["keywords_str"] = ", ".join(metadata["keywords"])
            for key, value in list(metadata.items()):
                if isinstance(value, (list, dict)):
                    metadata[key] = json.dumps(value, ensure_ascii=False)
            stream.write(
                json.dumps(
                    {
                        "id": metadata["chunk_id"],
                        "document": row["page_content"],
                        "metadata": metadata,
                        "embedding": [0.25, -0.5],
                    }
                )
                + "\n"
            )
    return path


def _rewrite_export(path, mutate):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    mutate(records)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _codes(catalog):
    return {f["code"] for f in catalog["findings"]}


@pytest.mark.parametrize(
    ("doc_type", "suffix"),
    [("jurisprudencia", ".pdf"), ("normativa", ".pdf"), ("normativa", ".md")],
)
def test_catalog_matches_export_without_claiming_live_or_legal_validation(
    tmp_path, doc_type, suffix
):
    row = _gold_row(doc_type=doc_type)
    corpus = _source(tmp_path, rows=[row], doc_type=doc_type)
    if suffix == ".md":
        (corpus / "raw" / doc_type / "caso.pdf").unlink()
        (corpus / "raw" / doc_type / "caso.md").write_text(
            "Fuente Markdown sintética", encoding="utf-8"
        )
    export = _export(tmp_path, [row])
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert catalog == build_catalog(tmp_path, corpus, export)
    assert _hashes(tmp_path) == before
    assert catalog["summary"]["source_files"] == 1
    assert catalog["summary"]["gold_records"] == 1
    assert catalog["summary"]["errors"] == 0
    assert catalog["inputs"]["export"]["ids_matched"] == 1
    assert catalog["inputs"]["export"]["records_with_metadata_differences"] == 0
    assert catalog["scope"]["live_index"] == "not_verified"
    assert catalog["scope"]["legal_validity"] == "not_verified"
    assert catalog["scope"]["pdf_check"] == "signature_only"
    assert catalog["documents"][0]["coverage"] == "not_verified"
    assert catalog["documents"][0]["observed_metadata"]["title"] == ["Título observado"]
    serialized = json.dumps(catalog)
    assert "private-do-not-publish" not in serialized
    assert '"embedding":' not in serialized
    assert "Texto sintético." not in serialized
    assert "Resumen" not in serialized
    assert str(tmp_path) not in serialized


def test_no_export_is_explicit_not_verified(tmp_path):
    catalog = build_catalog(tmp_path, _source(tmp_path))
    assert catalog["inputs"]["export"] is None
    assert "No se suministró backup" in render_markdown(catalog, tmp_path / "data", tmp_path)


def test_duplicate_bytes_are_reported_without_merging_sources_or_ids(tmp_path):
    a = _gold_row("uno", "uno_0")
    b = _gold_row("dos", "dos_0")
    corpus = _source(tmp_path, "uno", [a])
    _source(tmp_path, "dos", [b])
    export = _export(tmp_path, [a, b])
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert len(catalog["documents"]) == 2
    assert len(catalog["identical_source_groups"]) == 1
    assert catalog["inputs"]["export"]["ids_matched"] == 2
    assert "identical_source_bytes" in _codes(catalog)
    assert _hashes(tmp_path) == before


def test_metadata_and_text_differences_are_separate(tmp_path):
    row = _gold_row()
    corpus = _source(tmp_path, rows=[row])
    exported = json.loads(json.dumps(row))
    exported["metadata"]["summary"] = "Otro resumen"
    exported["metadata"]["keywords"] = ["pesca"]
    export = _export(tmp_path, [exported])
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["ids_matched"] == 1
    assert evidence["text_mismatches"] == 0
    assert evidence["records_with_metadata_differences"] == 1
    assert evidence["metadata_field_differences"] == {
        "keywords": 1,
        "keywords_str": 1,
        "summary": 1,
    }
    exported["page_content"] = "Otro texto"
    evidence = build_catalog(tmp_path, corpus, _export(tmp_path, [exported]))["inputs"]["export"]
    assert evidence["text_mismatches"] == 1


def test_ids_missing_in_each_snapshot_are_not_silently_associated(tmp_path):
    corpus = _source(tmp_path)
    export = _export(tmp_path, [_gold_row(cid="other_0")])
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["ids_matched"] == 0
    assert evidence["ids_missing_gold"] == 1
    assert evidence["gold_ids_missing_export"] == 1
    assert evidence["sources"][0]["records"] == 1


def test_duplicate_gold_id_is_ambiguous_not_last_record_wins(tmp_path):
    rows = [_gold_row(), _gold_row(text="Otro texto")]
    corpus = _source(tmp_path, rows=rows)
    catalog = build_catalog(tmp_path, corpus, _export(tmp_path, rows[:1]))
    assert catalog["summary"]["ambiguous_gold_ids"] == 1
    assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert catalog["inputs"]["export"]["ids_ambiguous_in_gold"] == 1
    assert "duplicate_gold_id" in _codes(catalog)


def test_duplicate_export_and_wrong_manifest_are_errors(tmp_path):
    row = _gold_row()
    corpus = _source(tmp_path)
    catalog = build_catalog(tmp_path, corpus, _export(tmp_path, [row, row], count=99))
    assert {"duplicate_export_id", "export_manifest_count_mismatch"} <= _codes(catalog)


@pytest.mark.parametrize("bad_line", ['{"page_content":', "[]", '{"x":1,"x":2}', '{"x":NaN}'])
def test_invalid_json_records_are_reported_not_validated(tmp_path, bad_line):
    corpus = _source(tmp_path)
    path = corpus / "gold/jurisprudencia/caso.jsonl"
    path.write_text(bad_line + "\n", encoding="utf-8")
    catalog = build_catalog(tmp_path, corpus)
    assert "invalid_json_record" in _codes(catalog)
    assert catalog["summary"]["errors"] > 0
    assert catalog["summary"]["gold_records"] == 0


def test_invalid_document_and_empty_file_are_reported(tmp_path):
    corpus = _source(tmp_path, rows=[{"page_content": "", "metadata": {}}])
    (corpus / "raw/jurisprudencia/caso.pdf").write_bytes(b"")
    catalog = build_catalog(tmp_path, corpus)
    assert {
        "empty_file",
        "invalid_pdf_signature",
        "empty_gold_chunk",
        "empty_silver_section",
    } <= _codes(catalog)


def test_empty_silver_sections_are_warnings_not_invalid_gold(tmp_path):
    corpus = _source(tmp_path)
    path = corpus / "silver/jurisprudencia/caso.jsonl"
    row = _gold_row(text="")
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    catalog = build_catalog(tmp_path, corpus)
    assert catalog["summary"]["errors"] == 0
    assert "empty_silver_section" in _codes(catalog)
    assert catalog["summary"]["gold_records"] == 1


def test_leading_whitespace_before_pdf_header_is_a_compatibility_warning(tmp_path):
    corpus = _source(tmp_path, binary=b"\t\n%PDF-1.4\nsynthetic")
    catalog = build_catalog(tmp_path, corpus)
    assert "pdf_header_offset" in _codes(catalog)
    assert "invalid_pdf_signature" not in _codes(catalog)
    assert catalog["summary"]["errors"] == 0


def test_input_change_during_audit_aborts_without_outputs(tmp_path, monkeypatch):
    _source(tmp_path)
    original = audit_local_corpus._inventory
    calls = 0

    def changing_inventory(*args):
        nonlocal calls
        calls += 1
        entries = original(*args)
        if calls > 1:
            entries[0]["sha256"] = "changed"
        return entries

    monkeypatch.setattr(audit_local_corpus, "_inventory", changing_inventory)
    assert main(["--project-root", str(tmp_path), "--write"]) == 2
    assert not (tmp_path / "data" / OUTPUT_NAMES[0]).exists()


def test_utf8_failure_and_corrupt_gzip_do_not_create_outputs(tmp_path):
    corpus = _source(tmp_path)
    (corpus / "raw/jurisprudencia/extra.md").write_bytes(b"\xff")
    assert "invalid_utf8" in _codes(build_catalog(tmp_path, corpus))
    export = tmp_path / "data/corrupt.gz"
    export.write_bytes(b"not gzip")
    assert main(["--project-root", str(tmp_path), "--export", "data/corrupt.gz", "--write"]) == 2
    assert not (tmp_path / "data" / OUTPUT_NAMES[0]).exists()


def test_unicode_mapping_preserves_exact_paths_and_reports_naming(tmp_path):
    name = unicodedata.normalize("NFD", "Senténcia  XXXX.")
    corpus = _source(tmp_path, name, [_gold_row(name)])
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus)
    assert {"unicode_non_nfc", "double_spaces", "placeholder_name", "trailing_dot"} <= _codes(
        catalog
    )
    assert catalog["documents"][0]["source_path"].endswith(name + ".pdf")
    assert "gold_source_type_mismatch" not in _codes(catalog)
    assert _hashes(tmp_path) == before


def test_two_raw_formats_same_stem_do_not_get_arbitrary_derivatives(tmp_path):
    corpus = _source(tmp_path)
    (corpus / "raw/jurisprudencia/caso.md").write_text("Original alternativo", encoding="utf-8")
    catalog = build_catalog(tmp_path, corpus)
    assert catalog["summary"]["source_files"] == 2
    assert "ambiguous_layer_mapping" in _codes(catalog)
    assert all(not doc["artifacts"] for doc in catalog["documents"])


def test_orphan_derivative_is_kept_visible(tmp_path):
    corpus = _source(tmp_path)
    (corpus / "raw/jurisprudencia/caso.pdf").unlink()
    catalog = build_catalog(tmp_path, corpus)
    assert catalog["summary"]["source_files"] == 0
    assert len(catalog["documents"]) == 1
    assert "missing_raw" in _codes(catalog)


def test_image_checks_resolve_encoded_paths_and_never_fetch_urls(tmp_path):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    (bronze / "con espacio.png").write_bytes(b"synthetic asset")
    (bronze / "caso.md").write_text(
        "![ok](con%20espacio.png)\n![missing](<missing.png>)\n"
        "![external](https://invalid.example/no-fetch.png)\n![outside](../../../secret.png)\n",
        encoding="utf-8",
    )
    catalog = build_catalog(tmp_path, corpus)
    assert len([f for f in catalog["findings"] if f["code"] == "missing_image"]) == 1
    assert "image_outside_corpus" in _codes(catalog)


@pytest.mark.parametrize(
    ("reference", "target", "legacy"),
    [
        ("![x](asset.png)", "asset.png", False),
        ("![x](<con espacio.png>)", "con espacio.png", False),
        ("![x](con%20espacio.png)", "con espacio.png", False),
        ('![x](asset.png "título con espacios")', "asset.png", False),
        ("![x](asset.png 'otro título')", "asset.png", False),
        ("![x](asset.png (título con espacios))", "asset.png", False),
        ('![x](<con espacio.png> "un título (con paréntesis)")', "con espacio.png", False),
        ("![x](asset.sinextensionconocida)", "asset.sinextensionconocida", False),
        ("![x](./nombre con espacios.png)", "nombre con espacios.png", True),
        ("![x](./nombre  con espacios.JPG)", "nombre  con espacios.JPG", True),
        ("![x](./Senténcia  y otros/assets/a.png)", "Senténcia  y otros/assets/a.png", True),
    ],
)
@pytest.mark.parametrize("exists", [True, False])
def test_image_destinations_are_complete_with_separate_syntax_warnings(
    tmp_path, reference, target, legacy, exists
):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    # NFD must not be normalized, either in the reference or on disk.
    reference, target = (unicodedata.normalize("NFD", value) for value in (reference, target))
    if exists:
        asset = bronze / target
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"synthetic asset")
    (bronze / "caso.md").write_text("Primera línea.\n" + reference + "\n", encoding="utf-8")
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus)
    images = [f for f in catalog["findings"] if f["code"].endswith("image")]
    assert len(images) == int(not exists)
    if images:
        assert images[0]["code"] == "missing_image"
        assert images[0]["line"] == 2
        assert Path(unquote(urlsplit(images[0]["detail"]).path)) == Path(target)
    assert ("unescaped_image_path" in _codes(catalog)) is legacy
    assert "unsupported_image_syntax" not in _codes(catalog)
    assert catalog == build_catalog(tmp_path, corpus)
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize(
    "reference",
    [
        "![x](asset.png título sin delimitar)",
        "![x](image(a).png)",
        "![x](image(a(b)).png)",
        "![x](<asset.png> título sin delimitar)",
        '![x](<con espacio.png> "título sin cierre)',
        "![x](nombre con espacios.unknown)",
        "![x](nombre con\nespacios.png)",
        "![x](https://invalid.example/con espacio.png)",
        "![x](/absolute/con espacio.png)",
        "![x](./con 'comillas'.png)",
        "![x]( ./con espacios.png)",
        "![x](./con espacios.png )",
    ],
)
def test_unsupported_image_syntax_never_reports_a_fragment_as_missing(tmp_path, reference):
    corpus = _source(tmp_path)
    (corpus / "bronze/jurisprudencia/caso.md").write_text(reference, encoding="utf-8")
    catalog = build_catalog(tmp_path, corpus)
    assert "missing_image" not in _codes(catalog)
    limitations = [f for f in catalog["findings"] if f["code"] == "unsupported_image_syntax"]
    assert len(limitations) == 1
    assert limitations[0]["line"] == 1
    assert "unescaped_image_path" not in _codes(catalog)


@pytest.mark.parametrize("middle_kind", ["directory", "missing", "file"])
@pytest.mark.parametrize("encoded", [False, True])
def test_parent_segments_check_the_literal_path_not_a_simplified_destination(
    tmp_path, middle_kind, encoded
):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    (bronze / "asset.png").write_bytes(b"synthetic asset")
    middle = bronze / "middle"
    if middle_kind == "directory":
        middle.mkdir()
    elif middle_kind == "file":
        middle.write_bytes(b"not a directory")
    target = "middle/%2E%2E/asset.png" if encoded else "middle/../asset.png"
    (bronze / "caso.md").write_text(f"![x]({target})\n", encoding="utf-8")
    before = _hashes(corpus)
    catalog = build_catalog(tmp_path, corpus)
    missing = [f for f in catalog["findings"] if f["code"] == "missing_image"]
    assert len(missing) == int(middle_kind != "directory")
    if missing:
        assert missing[0]["detail"] == target
        assert missing[0]["severity"] == "warning"
        assert missing[0]["line"] == 1
    assert catalog["summary"]["errors"] == 0
    assert _hashes(corpus) == before


@pytest.mark.parametrize("kind", ["file", "directory", "broken", "parent_traversal"])
def test_image_symlink_components_are_rejected_before_consulting_the_file(
    tmp_path, monkeypatch, kind
):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "asset.png").write_bytes(b"do not access")
    link = bronze / "link"
    if kind in ("directory", "parent_traversal"):
        link.symlink_to(outside, target_is_directory=True)
        target = "link/asset.png" if kind == "directory" else "link/../asset.png"
    else:
        link.symlink_to(outside / ("missing.png" if kind == "broken" else "asset.png"))
        target = "link"
    before = _hashes(outside)

    def forbidden(*args):
        pytest.fail("No consultar archivos ni resolver rutas a través de un symlink")

    monkeypatch.setattr(Path, "is_file", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    findings = []
    audit_local_corpus._audit_images(
        f"![x]({target})", bronze / "caso.md", tmp_path, corpus, findings
    )
    assert [f["code"] for f in findings] == ["image_symlink"]
    monkeypatch.undo()
    assert _hashes(outside) == before


def test_image_external_and_outside_destinations_never_access_files(tmp_path, monkeypatch):
    corpus = _source(tmp_path)

    def forbidden(*args):
        pytest.fail("No consultar candidatos externos")

    monkeypatch.setattr(Path, "is_file", forbidden)
    monkeypatch.setattr(Path, "is_symlink", forbidden)
    findings = []
    audit_local_corpus._audit_images(
        "![x](https://invalid.example/a.png) ![x](//invalid.example/a.png)\n"
        "![x](../../../../outside.png)",
        corpus / "bronze/jurisprudencia/caso.md",
        tmp_path,
        corpus,
        findings,
    )
    assert [f["code"] for f in findings] == ["image_outside_corpus"]


def test_image_catalog_write_and_check_preserve_inputs_without_site_packages(tmp_path):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    (bronze / "caso.md").write_text(
        "![x](./con espacios.png)\n![x](https://invalid.example/no-fetch.png)\n",
        encoding="utf-8",
    )
    (bronze / "con espacios.png").write_bytes(b"synthetic asset")
    before = _hashes(corpus)
    script = Path(__file__).resolve().parents[2] / "utils/audit_local_corpus.py"
    command = [sys.executable, "-I", "-S", str(script), "--project-root", str(tmp_path)]
    for mode in ("--write", "--check"):
        result = subprocess.run([*command, mode], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert _hashes(corpus) == before
    catalog = json.loads((tmp_path / "data/corpus-catalog.json").read_text())
    assert "unescaped_image_path" in _codes(catalog)
    assert "missing_image" not in _codes(catalog)
    outputs = _hashes(tmp_path / "data")
    assert main(["--project-root", str(tmp_path), "--check"]) == 0
    assert _hashes(tmp_path / "data") == outputs


def test_write_check_and_regeneration_are_deterministic_and_preserve_inputs(tmp_path):
    _source(tmp_path)
    args = ["--project-root", str(tmp_path)]
    before = _hashes(tmp_path / "data/documents")
    assert main([*args, "--check"]) == 1
    assert main([*args, "--write"]) == 0
    output_before = [(tmp_path / "data" / name).read_bytes() for name in OUTPUT_NAMES]
    assert main([*args, "--check"]) == 0
    assert main([*args, "--write"]) == 0
    assert output_before == [(tmp_path / "data" / name).read_bytes() for name in OUTPUT_NAMES]
    assert _hashes(tmp_path / "data/documents") == before
    (tmp_path / "data/documents/bronze/jurisprudencia/caso.md").write_text(
        "Cambio", encoding="utf-8"
    )
    assert main([*args, "--check"]) == 1
    assert output_before == [(tmp_path / "data" / name).read_bytes() for name in OUTPUT_NAMES]


@pytest.mark.parametrize("name", OUTPUT_NAMES)
def test_unrelated_output_files_are_not_overwritten(tmp_path, name):
    _source(tmp_path)
    target = tmp_path / "data" / name
    target.write_text(
        "{}" if target.suffix == ".json" else "Contenido del usuario", encoding="utf-8"
    )
    before = _hashes(tmp_path)
    assert main(["--project-root", str(tmp_path), "--write"]) == 2
    assert _hashes(tmp_path) == before


def test_reports_cannot_be_written_inside_corpus(tmp_path):
    _source(tmp_path)
    before = _hashes(tmp_path)
    assert main(["--project-root", str(tmp_path), "--output-dir", "data/documents", "--write"]) == 2
    assert _hashes(tmp_path) == before


def test_symlink_to_external_file_is_not_followed(tmp_path):
    corpus = _source(tmp_path)
    target = tmp_path / "external.txt"
    target.write_text("Do not read", encoding="utf-8")
    (corpus / "raw/jurisprudencia/link.md").symlink_to(target)
    with pytest.raises(ValueError, match="enlaces simbólicos"):
        build_catalog(tmp_path, corpus)


def test_cli_runs_without_site_packages_or_cloud_modules(tmp_path):
    corpus = _source(tmp_path)
    before = _hashes(corpus)
    script = Path(__file__).resolve().parents[2] / "utils/audit_local_corpus.py"
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(script), "--project-root", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Inventario técnico" in result.stdout
    assert _hashes(corpus) == before
    assert not (tmp_path / "data" / OUTPUT_NAMES[0]).exists()


def test_empty_or_wrong_layout_is_not_a_successful_corpus_validation(tmp_path):
    corpus = tmp_path / "data/documents"
    corpus.mkdir(parents=True)
    catalog = build_catalog(tmp_path, corpus)
    assert "no_corpus_documents" in _codes(catalog)
    assert catalog["summary"]["errors"] == 1


def test_metadata_serialization_differences_are_not_content_drift(tmp_path):
    row = _gold_row()
    row["metadata"]["entities"] = [{"name": "playa", "kind": "place"}]
    corpus = _source(tmp_path, rows=[row])
    export = _export(tmp_path, [row])
    with gzip.open(export, "rt", encoding="utf-8") as stream:
        lines = stream.readlines()
    record = json.loads(lines[1])
    record["metadata"]["entities"] = '[ { "kind": "place", "name": "playa" } ]'
    record["metadata"]["keywords"] = '[ "playa" ]'
    with gzip.open(export, "wt", encoding="utf-8") as stream:
        stream.write(lines[0] + json.dumps(record) + "\n")
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["records_with_metadata_differences"] == 0


def test_manifest_count_cannot_hide_invalid_export_record(tmp_path):
    corpus = _source(tmp_path)
    export = _export(tmp_path, [_gold_row()])
    with gzip.open(export, "rt", encoding="utf-8") as stream:
        lines = stream.readlines()
    record = json.loads(lines[1])
    record["embedding"] = []
    with gzip.open(export, "wt", encoding="utf-8") as stream:
        stream.write(lines[0] + json.dumps(record) + "\n")
    catalog = build_catalog(tmp_path, corpus, export)
    assert "invalid_export_record" in _codes(catalog)
    assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert catalog["summary"]["errors"] > 0


def test_output_symlink_cannot_overwrite_its_target(tmp_path):
    _source(tmp_path)
    external = tmp_path / "elsewhere.json"
    external.write_text("original", encoding="utf-8")
    (tmp_path / "data" / OUTPUT_NAMES[0]).symlink_to(external)
    assert main(["--project-root", str(tmp_path), "--write"]) == 2
    assert external.read_text() == "original"


def test_outside_project_inputs_and_outputs_are_refused(tmp_path):
    corpus = _source(tmp_path)
    with pytest.raises(ValueError, match="dentro del proyecto"):
        build_catalog(tmp_path / "other-project", corpus)
    before = _hashes(tmp_path)
    assert main(["--project-root", str(tmp_path), "--output-dir", "../outside", "--write"]) == 2
    assert _hashes(tmp_path) == before


def test_markdown_labels_are_escaped_and_links_are_portable(tmp_path):
    name = "caso [x]|<tag>"
    corpus = _source(tmp_path, name, [_gold_row(name)])
    md = render_markdown(build_catalog(tmp_path, corpus), tmp_path / "data", tmp_path)
    assert "\\[x\\]\\|&lt;tag&gt;" in md
    assert "%5Bx%5D%7C%3Ctag%3E" in md
    assert str(tmp_path) not in md


def test_complex_image_syntax_is_not_reported_as_a_partially_parsed_missing_file(tmp_path):
    corpus = _source(tmp_path)
    bronze = corpus / "bronze/jurisprudencia"
    (bronze / "image(a).png").write_bytes(b"synthetic")
    (bronze / "caso.md").write_text(
        "![angle](<image(a).png>)\n![complex](image(a).png)\n", encoding="utf-8"
    )
    catalog = build_catalog(tmp_path, corpus)
    assert "missing_image" not in _codes(catalog)


@pytest.mark.parametrize("field", ["source", "doc_type"])
@pytest.mark.parametrize("value", [[], {}, None, 17, False, "", "   "])
def test_invalid_export_source_types_are_reported_without_crashing(tmp_path, field, value):
    corpus = _source(tmp_path)
    export = _export(tmp_path, [_gold_row()])
    _rewrite_export(export, lambda records: records[1]["metadata"].update({field: value}))
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert "invalid_export_source_type" in _codes(catalog)
    assert catalog["summary"]["errors"] > 0
    assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert main(["--project-root", str(tmp_path), "--export", "data/snapshot.jsonl.gz"]) == 1
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize("invalid_first", [True, False])
@pytest.mark.parametrize("defect", ["keywords", "empty_text", "nontext"])
def test_gold_duplicates_remain_ambiguous_when_either_record_is_invalid(
    tmp_path, invalid_first, defect
):
    invalid = _gold_row()
    if defect == "keywords":
        invalid["metadata"]["keywords"] = [17]
    else:
        invalid["page_content"] = "" if defect == "empty_text" else 17
    valid = _gold_row()
    rows = [invalid, valid] if invalid_first else [valid, invalid]
    corpus = _source(tmp_path, rows=rows)
    export = _export(tmp_path, [valid])
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert "duplicate_gold_id" in _codes(catalog)
    assert catalog["summary"]["ambiguous_gold_ids"] == 1
    assert catalog["summary"]["gold_unique_comparable_ids"] == 0
    assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert catalog["inputs"]["export"]["ids_ambiguous_in_gold"] == 1
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize("invalid_first", [True, False])
@pytest.mark.parametrize(
    ("field", "value"), [("embedding", []), ("document", ""), ("metadata", [])]
)
def test_export_duplicates_are_detected_even_with_an_invalid_record(
    tmp_path, invalid_first, field, value
):
    corpus = _source(tmp_path)
    row = _gold_row()
    export = _export(tmp_path, [row, row])
    invalid_index = 1 if invalid_first else 2
    _rewrite_export(export, lambda records: records[invalid_index].update({field: value}))
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert {"invalid_export_record", "duplicate_export_id"} <= _codes(catalog)
    assert catalog["summary"]["errors"] >= 2
    if invalid_first:
        assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize("contents", ["", "\n", " \n\t\n"])
@pytest.mark.parametrize("with_export", [True, False])
def test_gold_file_without_records_cannot_pass_validation(tmp_path, contents, with_export):
    corpus = _source(tmp_path)
    (corpus / "gold/jurisprudencia/caso.jsonl").write_text(contents, encoding="utf-8")
    export = _export(tmp_path, [_gold_row()]) if with_export else None
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert catalog["summary"]["errors"] > 0
    assert ("empty_file" if not contents else "empty_gold_file") in _codes(catalog)
    assert catalog["summary"]["gold_records"] == 0
    args = ["--project-root", str(tmp_path)]
    if with_export:
        args += ["--export", "data/snapshot.jsonl.gz"]
    assert main(args) == 1
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize(
    "value", [{"z": [1, {"nested": "playa"}], "a": 2}, ["norma", {"id": 7}], []]
)
def test_other_structured_metadata_matches_serialization_without_publishing_values(tmp_path, value):
    row = _gold_row()
    row["metadata"]["references"] = value
    corpus = _source(tmp_path, rows=[row])
    export = _export(tmp_path, [row])
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    _rewrite_export(export, lambda records: records[1]["metadata"].update(references=serialized))
    before = _hashes(tmp_path)
    catalog = build_catalog(tmp_path, corpus, export)
    assert catalog["inputs"]["export"]["records_with_metadata_differences"] == 0
    assert catalog["summary"]["errors"] == 0
    assert "references" not in json.dumps(catalog)
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize("value", ['{"a":1,"z":2}', "[1, 2]", "2324", "true"])
def test_json_shaped_legal_strings_are_not_coerced_or_normalized(tmp_path, value):
    row = _gold_row()
    row["metadata"]["legal_reference"] = value
    corpus = _source(tmp_path, rows=[row])
    export = _export(tmp_path, [row])
    assert (
        build_catalog(tmp_path, corpus, export)["inputs"]["export"][
            "records_with_metadata_differences"
        ]
        == 0
    )
    decoded = json.loads(value)
    changed = (
        json.dumps(decoded, sort_keys=True, indent=2)
        if isinstance(decoded, (dict, list))
        else decoded
    )
    _rewrite_export(export, lambda records: records[1]["metadata"].update(legal_reference=changed))
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["metadata_field_differences"] == {"legal_reference": 1}


@pytest.mark.parametrize("replacement", ['{"a":9,"z":2}', '"not a container"', "broken JSON"])
def test_structured_metadata_real_differences_are_not_hidden(tmp_path, replacement):
    row = _gold_row()
    row["metadata"]["references"] = {"a": 1, "z": 2}
    corpus = _source(tmp_path, rows=[row])
    export = _export(tmp_path, [row])
    _rewrite_export(export, lambda records: records[1]["metadata"].update(references=replacement))
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["metadata_field_differences"] == {"references": 1}


def test_structured_metadata_list_order_is_significant(tmp_path):
    row = _gold_row()
    row["metadata"]["references"] = ["a", "b"]
    corpus = _source(tmp_path, rows=[row])
    export = _export(tmp_path, [row])
    _rewrite_export(export, lambda records: records[1]["metadata"].update(references='["b","a"]'))
    evidence = build_catalog(tmp_path, corpus, export)["inputs"]["export"]
    assert evidence["metadata_field_differences"] == {"references": 1}


def test_invalid_gold_duplicate_in_another_file_cannot_be_associated(tmp_path):
    invalid = _gold_row("uno", "shared_0")
    invalid["metadata"]["keywords"] = [17]
    valid = _gold_row("dos", "shared_0")
    corpus = _source(tmp_path, "uno", [invalid])
    _source(tmp_path, "dos", [valid])
    export = _export(tmp_path, [valid])
    catalog = build_catalog(tmp_path, corpus, export)
    assert "duplicate_gold_id" in _codes(catalog)
    assert catalog["summary"]["ambiguous_gold_ids"] == 1
    assert catalog["inputs"]["export"]["ids_matched"] == 0
    assert all(doc["export_records_matched_by_id"] == 0 for doc in catalog["documents"])


def test_invalid_export_can_be_reported_and_checked_without_rewriting_inputs(tmp_path):
    corpus = _source(tmp_path)
    export = _export(tmp_path, [_gold_row()])
    _rewrite_export(export, lambda records: records[1]["metadata"].update(doc_type=[]))
    before = _hashes(corpus)
    backup_before = export.read_bytes()
    args = ["--project-root", str(tmp_path), "--export", "data/snapshot.jsonl.gz"]
    assert main([*args, "--write"]) == 1
    report = json.loads((tmp_path / "data" / OUTPUT_NAMES[0]).read_text(encoding="utf-8"))
    assert "invalid_export_source_type" in _codes(report)
    outputs_before = [(tmp_path / "data" / name).read_bytes() for name in OUTPUT_NAMES]
    assert main([*args, "--check"]) == 1
    assert outputs_before == [(tmp_path / "data" / name).read_bytes() for name in OUTPUT_NAMES]
    assert _hashes(corpus) == before
    assert export.read_bytes() == backup_before


def test_invalid_export_metadata_does_not_prevent_comparing_later_valid_records(tmp_path):
    rows = [_gold_row(cid="caso_0"), _gold_row(cid="caso_1")]
    corpus = _source(tmp_path, rows=rows)
    export = _export(tmp_path, rows)
    _rewrite_export(export, lambda records: records[1]["metadata"].update(doc_type={}))
    catalog = build_catalog(tmp_path, corpus, export)
    assert catalog["summary"]["errors"] == 1
    assert "invalid_export_source_type" in _codes(catalog)
    assert catalog["inputs"]["export"]["records"] == 2
    assert catalog["inputs"]["export"]["ids_matched"] == 1
    assert catalog["inputs"]["export"]["records_with_metadata_differences"] == 0
