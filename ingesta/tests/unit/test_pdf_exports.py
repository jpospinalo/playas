"""Verifica la declaración pública sin importar Docling ni abrir servicios."""

import ast
from pathlib import Path


def test_pdf_public_exports_are_unique():
    init = Path(__file__).resolve().parents[2] / "ingest" / "pdf_to_md" / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    exports = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    assert len(exports) == len(set(exports))
    assert {"convert_pdfs_to_markdown", "process_single_pdf", "adaptive_cleanup"} <= set(exports)
