"""Contratos descriptivos de curación; solo JSON y fixtures sintéticos offline."""

import json
from copy import deepcopy
from datetime import date
from pathlib import Path, PurePosixPath

import pytest


def _assert_keys(value, expected):
    assert isinstance(value, dict)
    assert set(value) == set(expected.split())


def _assert_text(value, *, nullable=False):
    if nullable and value is None:
        return
    assert isinstance(value, str) and value.strip()


def _assert_sha256(value):
    _assert_text(value)
    assert len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _assert_contract(registry, catalog):
    """Comprueba estructura y asociación; no aprueba la verdad de las evidencias."""
    _assert_keys(
        registry,
        "schema_version scope labels_status legal_validation live_index references documents",
    )
    assert type(registry["schema_version"]) is int and registry["schema_version"] == 1
    assert registry["scope"] == "descriptive_only"
    assert registry["labels_status"] == "proposed"
    assert registry["legal_validation"] == "not_performed"
    assert registry["live_index"] == "not_verified"
    references = registry["references"]
    _assert_keys(references, "normativa_legacy sentencias_legacy diagnostic")
    for reference in references.values():
        _assert_keys(reference, "filename sha256")
        _assert_text(reference["filename"])
        assert "/" not in reference["filename"] and "\\" not in reference["filename"]
        _assert_sha256(reference["sha256"])

    documents = registry["documents"]
    assert isinstance(documents, list)
    assert len(documents) == len(catalog["documents"])
    paths = []
    for document, source in zip(documents, catalog["documents"], strict=True):
        _assert_keys(
            document,
            "source_path source_sha256 display_label identity representation selection evidence notes",
        )
        _assert_text(document["source_path"])
        path = PurePosixPath(document["source_path"])
        assert not path.is_absolute() and ".." not in path.parts
        assert path.parts[:3] == ("data", "documents", "raw") and len(path.parts) > 3
        assert document["source_path"] == source["source_path"]
        _assert_sha256(document["source_sha256"])
        assert document["source_sha256"] == source["sha256"]
        paths.append(document["source_path"])
        _assert_text(document["display_label"])
        assert document["representation"] in {"excerpt", "extent_unverified"}

        identity = document["identity"]
        _assert_keys(
            identity, "status kind number year issuer jurisdiction decision_date case_reference"
        )
        assert identity["status"] in {"supported_locally", "provisional"}
        for key in ("kind", "number", "issuer", "jurisdiction", "case_reference"):
            _assert_text(identity[key], nullable=True)
        doc_type = source["doc_type"]
        assert doc_type in {"normativa", "jurisprudencia"}
        if doc_type == "normativa":
            assert identity["year"] is None or type(identity["year"]) is int
            assert identity["decision_date"] is None and identity["case_reference"] is None
        else:
            assert identity["year"] is None
            if identity["decision_date"] is not None:
                _assert_text(identity["decision_date"])
                assert (
                    date.fromisoformat(identity["decision_date"]).isoformat()
                    == identity["decision_date"]
                )

        selection = document["selection"]
        _assert_keys(selection, "mode literal targets")
        mode = selection["mode"]
        assert mode in {"selected", "whole_declared", "conflicting", "unknown", "not_applicable"}
        targets = selection["targets"]
        assert isinstance(targets, list)
        for target in targets:
            _assert_keys(target, "article fragment")
            _assert_text(target["article"])
            _assert_text(target["fragment"], nullable=True)
        if mode in {"unknown", "not_applicable"}:
            assert selection["literal"] is None and not targets
        else:
            _assert_text(selection["literal"])
            if mode == "selected":
                assert targets
            elif mode == "whole_declared":
                assert not targets
        assert (mode == "not_applicable") == (doc_type == "jurisprudencia")

        notes = document["notes"]
        assert isinstance(notes, list)
        for note in notes:
            _assert_text(note)
        evidence = document["evidence"]
        assert isinstance(evidence, list) and evidence
        for entry in evidence:
            _assert_keys(entry, "reference locator role")
            assert entry["reference"] in {*references, "raw", "bronze"}
            _assert_text(entry["locator"])
            assert entry["role"] in {"identity", "selection", "representation", "conflict"}
        assert any(e["role"] == "identity" for e in evidence)
        if identity["status"] == "supported_locally":
            assert any(e["reference"] == "raw" and e["role"] == "identity" for e in evidence)
        else:
            assert notes
        if mode in {"selected", "whole_declared", "conflicting"}:
            assert any(
                e["reference"] == "normativa_legacy" and e["role"] == "selection" for e in evidence
            )
        if mode == "conflicting":
            assert notes and any(e["role"] == "conflict" for e in evidence)
        if document["representation"] == "excerpt":
            assert any(e["reference"] == "raw" and e["role"] == "representation" for e in evidence)

    assert len(paths) == len(set(paths))
    serialized = json.dumps(registry, ensure_ascii=False)
    assert "/Users/" not in serialized
    assert "sharepoint.com" not in serialized.lower()


def _sample():
    """Dos documentos pequeños; no copias del corpus ni archivos fuente."""
    documents = []
    for doc_type, name, digest in [
        ("normativa", "cafe\u0301.pdf", "a" * 64),
        ("jurisprudencia", "caso.pdf", "b" * 64),
    ]:
        is_norm = doc_type == "normativa"
        documents.append(
            {
                "source_path": f"data/documents/raw/{doc_type}/{name}",
                "source_sha256": digest,
                "display_label": "Documento de prueba",
                "identity": {
                    "status": "provisional" if is_norm else "supported_locally",
                    "kind": "Decreto" if is_norm else "Sentencia",
                    "number": "007" if is_norm else None,
                    "year": 2024 if is_norm else None,
                    "issuer": None,
                    "jurisdiction": None,
                    "decision_date": None if is_norm else "2024-02-29",
                    "case_reference": None if is_norm else "0007-01",
                },
                "representation": "extent_unverified",
                "selection": {
                    "mode": "selected" if is_norm else "not_applicable",
                    "literal": "Art. 007 y paragrafo 1 \n" if is_norm else None,
                    "targets": [{"article": "007", "fragment": "y paragrafo 1"}] if is_norm else [],
                },
                "evidence": [
                    {"reference": "raw", "locator": "Página 1", "role": "identity"},
                    {
                        "reference": "normativa_legacy",
                        "locator": "Nacional!G2",
                        "role": "selection",
                    },
                ],
                "notes": ["Pendiente de confirmación."] if is_norm else [],
            }
        )
    registry = {
        "schema_version": 1,
        "scope": "descriptive_only",
        "labels_status": "proposed",
        "legal_validation": "not_performed",
        "live_index": "not_verified",
        "references": {
            name: {"filename": filename, "sha256": "c" * 64}
            for name, filename in [
                ("normativa_legacy", "normativa.xlsx"),
                ("sentencias_legacy", "sentencias.xlsx"),
                ("diagnostic", "diagnostico.md"),
            ]
        },
        "documents": documents,
    }
    catalog = {
        "documents": [
            {"source_path": d["source_path"], "sha256": d["source_sha256"], "doc_type": doc_type}
            for d, doc_type in zip(documents, ("normativa", "jurisprudencia"), strict=True)
        ]
    }
    return registry, catalog


@pytest.mark.parametrize("mode", ["selected", "whole_declared", "conflicting", "unknown"])
def test_accepts_selection_modes_without_mutating_literals_or_fragments(mode):
    registry, catalog = _sample()
    selection = registry["documents"][0]["selection"]
    selection["mode"] = mode
    if mode == "whole_declared":
        selection.update(literal="Todo el decreto \n", targets=[])
    elif mode == "unknown":
        selection.update(literal=None, targets=[])
    elif mode == "conflicting":
        registry["documents"][0]["evidence"].append(
            {"reference": "diagnostic", "locator": "Conflicto documentado", "role": "conflict"}
        )
    before = deepcopy((registry, catalog))
    _assert_contract(registry, catalog)
    assert (registry, catalog) == before
    assert registry["documents"][0]["identity"]["number"] == "007"


def test_accepts_distinct_paths_with_identical_hashes_labels_and_identities():
    registry, catalog = _sample()
    duplicate = deepcopy(registry["documents"][0])
    duplicate["source_path"] = "data/documents/raw/normativa/otra-copia.pdf"
    registry["documents"].append(duplicate)
    catalog["documents"].append(
        {
            "source_path": duplicate["source_path"],
            "sha256": duplicate["source_sha256"],
            "doc_type": "normativa",
        }
    )
    _assert_contract(registry, catalog)


def test_accepts_unknown_optional_identity_and_does_not_require_all_sources_supported():
    registry, catalog = _sample()
    for document in registry["documents"]:
        document["identity"].update(
            status="provisional",
            kind=None,
            number=None,
            year=None,
            issuer=None,
            jurisdiction=None,
            decision_date=None,
            case_reference=None,
        )
        document["notes"] = ["Identidad pendiente."]
    _assert_contract(registry, catalog)


@pytest.mark.parametrize("article", ["007", "2.3.4", "1.2A.3"])
def test_preserves_string_identifiers_and_unspecified_fragments(article):
    registry, catalog = _sample()
    selection = registry["documents"][0]["selection"]
    selection.update(literal=f"Art. {article} \n", targets=[{"article": article, "fragment": None}])
    before = deepcopy(selection)
    _assert_contract(registry, catalog)
    assert selection == before


def test_excerpt_requires_primary_representation_evidence():
    registry, catalog = _sample()
    document = registry["documents"][0]
    document["representation"] = "excerpt"
    with pytest.raises(AssertionError):
        _assert_contract(registry, catalog)
    document["evidence"].append(
        {"reference": "raw", "locator": "Página original 20", "role": "representation"}
    )
    _assert_contract(registry, catalog)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param(("schema_version",), True, id="version-bool"),
        pytest.param(("schema_version",), 2, id="version-unsupported"),
        pytest.param(("scope",), "runtime", id="scope-runtime"),
        pytest.param(("labels_status",), "approved", id="labels-approved"),
        pytest.param(("legal_validation",), "approved", id="legal-approved"),
        pytest.param(("live_index",), "verified", id="live-verified"),
        pytest.param(("runtime",), {}, id="extra-root-field"),
        pytest.param(("references", "extra"), {}, id="extra-reference"),
        pytest.param(("references", "diagnostic", "url"), "private", id="extra-reference-field"),
        pytest.param(("references", "diagnostic", "sha256"), "bad", id="reference-hash"),
        pytest.param(
            ("references", "diagnostic", "filename"), "outside/report.md", id="reference-path"
        ),
        pytest.param(("documents",), (), id="documents-not-list"),
        pytest.param(("documents", 0, "source_path"), "/absolute/file.pdf", id="absolute-source"),
        pytest.param(
            ("documents", 0, "source_path"), "data/documents/raw/../file.pdf", id="parent-source"
        ),
        pytest.param(("documents", 0, "source_path"), "data/gold/file.jsonl", id="outside-raw"),
        pytest.param(("documents", 0, "source_sha256"), "bad", id="source-hash-invalid"),
        pytest.param(("documents", 0, "source_sha256"), "d" * 64, id="source-hash-different"),
        pytest.param(("documents", 0, "display_label"), " ", id="empty-label"),
        pytest.param(("documents", 0, "runtime_metadata"), {}, id="extra-document-field"),
        pytest.param(
            ("documents", 0, "representation"), "complete_validated", id="representation-certified"
        ),
        pytest.param(("documents", 0, "identity", "status"), "approved", id="identity-approved"),
        pytest.param(("documents", 0, "identity", "year"), True, id="year-bool"),
        pytest.param(("documents", 0, "identity", "year"), "2024", id="year-string"),
        pytest.param(("documents", 0, "identity", "number"), 7, id="number-not-string"),
        pytest.param(("documents", 0, "identity", "issuer"), "", id="empty-optional-string"),
        pytest.param(
            ("documents", 0, "identity", "decision_date"),
            "2024-01-01",
            id="normative-decision-date",
        ),
        pytest.param(("documents", 0, "identity", "case_reference"), "case", id="normative-case"),
        pytest.param(
            ("documents", 0, "identity", "instance"), "Segunda", id="extra-identity-field"
        ),
        pytest.param(("documents", 1, "identity", "year"), 2024, id="judicial-year"),
        pytest.param(
            ("documents", 1, "identity", "decision_date"), "2025-02-29", id="impossible-date"
        ),
        pytest.param(
            ("documents", 1, "identity", "decision_date"), "20240229", id="noncanonical-date"
        ),
        pytest.param(("documents", 0, "selection", "mode"), "all", id="invalid-mode"),
        pytest.param(("documents", 0, "selection", "approved"), True, id="extra-selection-field"),
        pytest.param(
            ("documents", 0, "selection", "mode"), "not_applicable", id="normative-not-applicable"
        ),
        pytest.param(("documents", 0, "selection", "literal"), " ", id="selected-empty-literal"),
        pytest.param(("documents", 0, "selection", "targets"), [], id="selected-empty-targets"),
        pytest.param(("documents", 0, "selection", "targets"), (), id="targets-not-list"),
        pytest.param(
            ("documents", 0, "selection", "targets", 0, "article"), 7, id="article-not-string"
        ),
        pytest.param(
            ("documents", 0, "selection", "targets", 0, "article"), "", id="article-empty"
        ),
        pytest.param(
            ("documents", 0, "selection", "targets", 0, "fragment"), "", id="fragment-empty"
        ),
        pytest.param(
            ("documents", 0, "selection", "targets", 0, "approved"), True, id="extra-target-field"
        ),
        pytest.param(("documents", 0, "evidence"), [], id="evidence-empty"),
        pytest.param(("documents", 0, "evidence"), (), id="evidence-not-list"),
        pytest.param(
            ("documents", 0, "evidence", 0, "reference"), "gold", id="evidence-unknown-reference"
        ),
        pytest.param(("documents", 0, "evidence", 0, "locator"), " ", id="evidence-empty-locator"),
        pytest.param(
            ("documents", 0, "evidence", 0, "role"), "approved", id="evidence-invalid-role"
        ),
        pytest.param(("documents", 0, "evidence", 0, "url"), "private", id="extra-evidence-field"),
        pytest.param(("documents", 0, "notes"), [], id="provisional-without-notes"),
        pytest.param(("documents", 0, "notes"), (), id="notes-not-list"),
        pytest.param(("documents", 0, "notes"), [""], id="empty-note"),
    ],
)
def test_rejects_invalid_fields(path, value):
    registry, catalog = _sample()
    target = registry
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises((AssertionError, ValueError)):
        _assert_contract(registry, catalog)


@pytest.mark.parametrize(
    "change", ["missing", "extra", "reordered", "repeated", "unicode-normalized"]
)
def test_rejects_source_sequence_changes(change):
    registry, catalog = _sample()
    documents = registry["documents"]
    if change == "missing":
        documents.pop()
    elif change == "extra":
        documents.append(deepcopy(documents[0]))
    elif change == "reordered":
        documents.reverse()
    elif change == "repeated":
        documents[1] = deepcopy(documents[0])
        catalog["documents"][1] = deepcopy(catalog["documents"][0])
    else:
        documents[0]["source_path"] = "data/documents/raw/normativa/café.pdf"
    with pytest.raises(AssertionError):
        _assert_contract(registry, catalog)


@pytest.mark.parametrize("mode", ["whole_declared", "unknown", "not_applicable"])
def test_rejects_undeclared_expansion(mode):
    registry, catalog = _sample()
    selection = registry["documents"][0 if mode != "not_applicable" else 1]["selection"]
    selection.update(
        mode=mode,
        literal="Todo el decreto" if mode == "whole_declared" else None,
        targets=[{"article": "1", "fragment": None}],
    )
    with pytest.raises(AssertionError):
        _assert_contract(registry, catalog)


@pytest.mark.parametrize("missing", ["notes", "conflict", "selection"])
def test_conflicting_selection_requires_explanation_and_both_evidence_roles(missing):
    registry, catalog = _sample()
    document = registry["documents"][0]
    document["selection"]["mode"] = "conflicting"
    document["evidence"].append(
        {"reference": "diagnostic", "locator": "Conflicto", "role": "conflict"}
    )
    if missing == "notes":
        document["notes"] = []
    else:
        document["evidence"] = [e for e in document["evidence"] if e["role"] != missing]
    with pytest.raises(AssertionError):
        _assert_contract(registry, catalog)


def test_supported_identity_requires_raw_evidence():
    registry, catalog = _sample()
    registry["documents"][1]["evidence"][0]["reference"] = "sentencias_legacy"
    with pytest.raises(AssertionError):
        _assert_contract(registry, catalog)


def test_published_registry_matches_only_the_versioned_json_catalog():
    root = Path(__file__).resolve().parents[3]
    path = root / "data/corpus-curation.json"
    encoded = path.read_bytes()
    registry = json.loads(encoded.decode("utf-8"))
    catalog = json.loads((root / "data/corpus-catalog.json").read_text(encoding="utf-8"))
    _assert_contract(registry, catalog)
    assert encoded == (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
