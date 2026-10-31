"""Offline contracts for image preservation during footnote cleanup."""

from urllib.parse import quote

import pytest
from PIL import Image

from ingest.pdf_to_md.text_cleanup import remove_footnote_numbers


@pytest.mark.parametrize("alt", ["", "a", "Image14"])
@pytest.mark.parametrize("delimited", [False, True])
@pytest.mark.parametrize(
    "name",
    [
        "a.png",
        "a b.png",
        "á é.png",
        "Café.png",
        "a%20b.png",
        "a%literal b.png",
        "a#?&.png",
        "a<>.png",
        "foto (anexo).png",
        "foto((anexo)).png",
        "carpeta (anexo)/foto.png",
    ],
)
def test_c2_absolute_destination_is_complete_and_encoded_once(tmp_path, name, delimited, alt):
    from urllib.parse import unquote

    from ingest.pdf_to_md.images import relativize_image_refs

    asset = tmp_path / name
    raw = f"<{asset}>" if delimited else str(asset)
    source = f"Prosa14 ![{alt}]({raw}) exterior 6."
    if delimited and name == "a<>.png":
        assert relativize_image_refs(source, tmp_path / "documento.md") == source
        return
    destination = quote(f"./{name}", safe="/._-~")
    expected = f"Prosa14 ![{alt}]({destination}) exterior 6."
    result = relativize_image_refs(source, tmp_path / "documento.md")
    assert result == expected
    assert unquote(destination) == f"./{name}"
    assert relativize_image_refs(result, tmp_path / "documento.md") == result
    token = f"![{alt}]({destination})"
    assert remove_footnote_numbers(token) == token
    assert not asset.exists()


@pytest.mark.parametrize(
    "destination",
    [
        "a.png",
        "./a.png",
        "./á.png",
        "./a%20b.png",
        "./a%25b.png",
        "./a#b.png",
        "./a?b.png",
        "./a&b.png",
        "<./a b.png>",
        "<./foto(anexo).png>",
        "./a%20b c.png",
        "./a%25b c.png",
        "./a%20b(c).png",
        "https://example.com/a(b).png",
        "http://example.com/a%20b.png",
        "//example.com/a.png",
        "data:image/png;base64,abcd",
        "file:///tmp/a.png",
    ],
)
def test_c2_existing_relative_or_external_reference_stays_literal(
    tmp_path, monkeypatch, destination
):
    from ingest.pdf_to_md.images import relativize_image_refs

    source = f"Antes ![a]({destination}) después."
    md_path = tmp_path / "documento.md"
    # Exercise a cwd where the old implementation can accidentally reinterpret
    # a relative reference as a path under the Markdown directory.
    monkeypatch.chdir(tmp_path)
    assert relativize_image_refs(source, md_path) == source
    elsewhere = tmp_path / "otro"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert relativize_image_refs(source, md_path) == source


@pytest.mark.parametrize(
    ("raw", "encoded"),
    [
        ("./a b.png", "./a%20b.png"),
        ("a b.png", "a%20b.png"),
        ("../a b.png", "../a%20b.png"),
        ("./a%literal b.png", "./a%25literal%20b.png"),
        ("./foto(anexo).png", "./foto%28anexo%29.png"),
        ("./Prueba<>.png", "./Prueba%3C%3E.png"),
    ],
)
def test_c2_raw_relative_path_is_encoded_without_cwd_resolution(
    tmp_path, monkeypatch, raw, encoded
):
    from ingest.pdf_to_md.images import relativize_image_refs

    source = f"![a]({raw})"
    md_path = tmp_path / "documento.md"
    monkeypatch.chdir(tmp_path)
    result = relativize_image_refs(source, md_path)
    assert result == f"![a]({encoded})"
    assert relativize_image_refs(result, md_path) == result
    elsewhere = tmp_path / "otro"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert relativize_image_refs(source, md_path) == result


@pytest.mark.parametrize("delimited", [False, True])
@pytest.mark.parametrize("title", ['"nota"', "'nota'", "(nota)"])
def test_c2_titles_are_not_part_of_the_filesystem_path(tmp_path, delimited, title):
    from ingest.pdf_to_md.images import relativize_image_refs

    path = str(tmp_path / "foto.png")
    raw = f"<{path}>" if delimited else path
    source = f"![a]({raw} {title})"
    assert relativize_image_refs(source, tmp_path / "documento.md") == source


def test_c2_delimiters_disambiguate_parentheses_inside_filename(tmp_path):
    from ingest.pdf_to_md.images import relativize_image_refs

    raw = str(tmp_path / "foto (anexo)")
    md_path = tmp_path / "documento.md"
    bare = f"![a]({raw})"
    assert relativize_image_refs(bare, md_path) == bare
    assert relativize_image_refs(f"![a](<{raw}>)", md_path) == "![a](./foto%20%28anexo%29)"


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "(incompleta)",
        "\\nombre.png)",
        "a\tb.png)",
        "a\x00b.png)",
        "<incompleta)",
        "<a<b>.png>)",
    ],
)
def test_c2_malformed_candidate_does_not_rewrite_a_prefix(tmp_path, suffix):
    from ingest.pdf_to_md.images import relativize_image_refs

    candidate = suffix if suffix.startswith("<") else f"{tmp_path}/{suffix}"
    source = f"![a]({candidate} ![b]({tmp_path}/valida.png)"
    assert relativize_image_refs(source, tmp_path / "documento.md") == source


def test_c2_multiple_tokens_preserve_order_alt_and_exterior(tmp_path):
    from ingest.pdf_to_md.images import relativize_image_refs

    first = tmp_path / "foto((anexo)).png"
    second = tmp_path / "a b.png"
    source = f"Antes ![14]({first}) entre ![]({second}) después ![14]({first})."
    expected = (
        "Antes ![14](./foto%28%28anexo%29%29.png) entre ![](./a%20b.png) "
        "después ![14](./foto%28%28anexo%29%29.png)."
    )
    assert relativize_image_refs(source, tmp_path / "documento.md") == expected


def test_c2_external_absolute_and_non_image_link_are_untouched(tmp_path):
    from ingest.pdf_to_md.images import relativize_image_refs

    outside = tmp_path.parent / "fuera (anexo).png"
    source = f"![a]({outside}) y [enlace]({tmp_path}/a b.png)"
    assert relativize_image_refs(source, tmp_path / "documento.md") == source


@pytest.mark.parametrize("position", ["preamble", "body"])
@pytest.mark.parametrize("alt", ["", "a"])
@pytest.mark.parametrize("caption", ["Mapa", "Fig. 1"])
@pytest.mark.parametrize(
    "name",
    [
        "a b.png",
        "á é.png",
        "foto (anexo).png",
        "a%20b.png",
        "Documento" + "a" * 39 + " de/assets/image_" + "1234567890" * 6 + "ab87.png",
    ],
)
def test_c2_serialization_connects_to_real_cleanup(tmp_path, position, alt, caption, name):
    from ingest.pdf_to_md.cleaner import adaptive_cleanup
    from ingest.pdf_to_md.images import _resolve_image_path, relativize_image_refs
    from ingest.pdf_to_md.models import LegalDocumentProfile

    asset = tmp_path / name
    asset.parent.mkdir(parents=True, exist_ok=True)
    pixels = (bytes(range(256)) * 977)[:250000]
    with Image.frombytes("L", (500, 500), pixels) as image:
        image.save(asset)
    original = asset.read_bytes()
    raw_token = f"![{alt}]({asset})"
    line = f"{caption} {raw_token}"
    tail = "\n\n## Consideraciones\nFigura de prueba para el expediente.\n"
    source = line + tail if position == "preamble" else "## Inicio\n\n" + line + tail
    md_path = tmp_path / "documento.md"
    serialized = relativize_image_refs(source, md_path)
    destination = quote(f"./{name}", safe="/._-~")
    token = f"![{alt}]({destination})"
    assert serialized == source.replace(raw_token, token)
    assert relativize_image_refs(serialized, md_path) == serialized
    assert _resolve_image_path(destination, tmp_path) == asset.resolve()
    result = adaptive_cleanup(serialized, LegalDocumentProfile(), md_path)
    assert token in result
    assert caption in result
    assert asset.read_bytes() == original


@pytest.mark.parametrize("representation", ["legacy", "angles", "quote"])
@pytest.mark.parametrize(
    ("caption", "folder_size"),
    [("Figura del expediente", 26), ("Mapa", 39)],
)
def test_mixed_frontmatter_known_boundary_is_preserved(caption, folder_size, representation):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    target = "./Documento" + "a" * folder_size + " de/assets/image_" + "1234567890" * 6 + "ab87.png"
    destination = (
        f"<{target}>"
        if representation == "angles"
        else quote(target, safe="/._-~")
        if representation == "quote"
        else target
    )
    line = f"{caption} ![Image]({destination})"
    source = line + "\n\n## Consideraciones\nTexto jurídico."
    assert strip_frontmatter_noise(source) == source


@pytest.mark.parametrize("caption", ["A", "XY", "Mapa", "MAPA", "Á", "á", "Fig. 2021", "ANEXO I"])
@pytest.mark.parametrize("placement", ["before", "after", "around", "multiple"])
@pytest.mark.parametrize("representation", ["legacy", "angles", "quote"])
def test_mixed_frontmatter_labels_are_structural(caption, placement, representation):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    target = "./Expediente marítimo/assets/image_" + "1234567890" * 6 + "ab87.png"
    destination = (
        f"<{target}>"
        if representation == "angles"
        else quote(target, safe="/._-~")
        if representation == "quote"
        else target
    )
    token = f"![]({destination})"
    line = {
        "before": f"{caption} {token}",
        "after": f"{token} {caption}",
        "around": f"{caption} {token} texto",
        "multiple": f"{caption}\t{token} {token}",
    }[placement]
    source = "\t" + line + "  \n\n## Consideraciones\nTexto jurídico."
    assert strip_frontmatter_noise(source) == source


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("123 ![a](1234567890.png)", False),
        ("@ruido ![a](x.png)", False),
        ("#ruido ![a](x.png)", False),
        ("1234567890 texto ![a](x.png)", False),
        ("`![a](1234567890.png)`", False),
        (r"\![a](1234567890.png)", False),
        ("A ![a](1234567890.png) ![incompleta](", False),
        ("A ![a]()", False),
        ('A ![a](1234567890.png "123")', False),
        ("A ![a](1234567890(87).png)", False),
        ("TRIBUNAL ADMINISTRATIVO", False),
        ("MAPA", False),
        ("Texto jurídico suficiente para la valoración.", True),
        ("Texto suficientemente largo `![a](x.png)`", True),
        (r"Texto suficientemente largo \![a](x.png)", True),
    ],
)
def test_mixed_frontmatter_noise_and_ambiguity_keep_fallback(line, kept):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    suffix = "\n\n## Consideraciones\nTexto jurídico."
    source = line + suffix
    assert strip_frontmatter_noise(source) == (source if kept else suffix[1:])


@pytest.mark.parametrize("representation", ["legacy", "angles", "quote"])
def test_mixed_frontmatter_token_metadata_does_not_classify_label(representation):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    target = "./Expediente #@14/assets/image_" + "1234567890" * 6 + "ab87.png"
    destination = (
        f"<{target}>"
        if representation == "angles"
        else quote(target, safe="/._-~")
        if representation == "quote"
        else target
    )
    line = f"A ![#@14]({destination})"
    source = line + "\n\n## Consideraciones\nTexto jurídico."
    assert strip_frontmatter_noise(source) == source


@pytest.mark.parametrize("position", ["preamble", "body"])
@pytest.mark.parametrize("representation", ["legacy", "angles", "quote"])
@pytest.mark.parametrize(
    ("caption", "folder_size"),
    [("Figura del expediente", 26), ("Mapa", 39), ("A", 39), ("Fig. 2021", 39)],
)
def test_mixed_image_survives_real_cleanup(
    tmp_path, position, representation, caption, folder_size
):
    from ingest.pdf_to_md.cleaner import adaptive_cleanup
    from ingest.pdf_to_md.models import LegalDocumentProfile

    target = "./Documento" + "a" * folder_size + " de/assets/image_" + "1234567890" * 6 + "ab87.png"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    pixels = (bytes(range(256)) * 977)[: 500 * 500]
    with Image.frombytes("L", (500, 500), pixels) as image:
        image.save(path)
    original_bytes = path.read_bytes()
    destination = (
        f"<{target}>"
        if representation == "angles"
        else quote(target, safe="/._-~")
        if representation == "quote"
        else target
    )
    token = f"![Image]({destination})"
    line = f"{caption} {token}"
    suffix = "\n\n## Consideraciones\nFigura de prueba para el expediente.\n"
    source = line + suffix if position == "preamble" else "## Consideraciones\n\n" + line + suffix
    result = adaptive_cleanup(source, LegalDocumentProfile(), tmp_path / "documento.md")
    assert token in result
    assert caption in result
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("ending", ["abc7", "abc87", "20228", "9f2a"])
@pytest.mark.parametrize(
    "destination",
    [
        "./assets/image_{hash}.png",
        "<./Fallo marítimo/assets/image_{hash}.png>",
        "./Fallo%20mar%C3%ADtimo/assets/image_{hash}.png",
    ],
)
@pytest.mark.parametrize("suffix", ["", "\n"])
def test_image_hash_and_alt_are_preserved(ending, destination, suffix):
    digest = "a" * (64 - len(ending)) + ending
    token = f"![Figura14 de 20228]({destination.format(hash=digest)})"
    assert remove_footnote_numbers(token + suffix) == token + suffix


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("jurisdicción14", "jurisdicción"),
        ("contestó 6", "contestó"),
        ("INVEMAR) 13", "INVEMAR)"),
        ("20228", "2022"),
        ("2021 32 ,", "2021 ,"),
        ("CPT-CAM-012-21 34", "CPT-CAM-012-21"),
        ("artículo 14", "artículo 14"),
        ("ley 99", "ley 99"),
        ("decreto 2324", "decreto 2324"),
        ("contestó 56", "contestó 56"),
        ("contestó 123", "contestó 123"),
        ("artículo jurisdicción14", "artículo jurisdicción14"),
        ("ley contestó 6", "ley contestó 6"),
        ("", ""),
    ],
)
def test_prose_keeps_existing_six_pass_contract(source, expected):
    assert remove_footnote_numbers(source) == expected


def test_multiple_and_repeated_images_with_external_notes():
    first = "![Figura14](<./Documento 20228/assets/image_" + "b" * 62 + "87.png>)"
    second = "![Plano 32](./assets/image_" + "c" * 63 + "7.png)"
    source = f"jurisdicción14 {first} contestó 6\n{second}\n{first}\n20228"
    expected = f"jurisdicción {first} contestó\n{second}\n{first}\n2022"
    assert remove_footnote_numbers(source) == expected


def test_cross_boundary_match_preserves_the_whole_match():
    token = "![Figura](./assets/image_abc87.png)"
    source = f"{token} 13 y contestó 6"
    assert remove_footnote_numbers(source) == f"{token} 13 y contestó"


def test_image_remains_in_legal_callback_lookback():
    # The image separates 'ley' from the word: legal context must not leak
    # across it through token removal or placeholders.
    token = "![a](x.png)"
    source = f"ley {token} contestó 6"
    assert remove_footnote_numbers(source) == f"ley {token} contestó"


def test_each_pass_recomputes_image_offsets():
    token = "![CPT-CAM-012-21 34 y 2021 32 ,](<./assets/image_abc87.png>)"
    source = f"jurisdicción14 contestó 6 INVEMAR) 13 20228\n{token}\n2021 32 ,"
    expected = f"jurisdicción contestó INVEMAR) 2022\n{token}\n2021 ,"
    assert remove_footnote_numbers(source) == expected


@pytest.mark.parametrize("position", ["preamble", "body"])
@pytest.mark.parametrize("representation", ["legacy", "angles", "quote"])
def test_g2a_standalone_image_survives_real_cleanup(tmp_path, position, representation):
    """All representations survive; no protected cleanup stage is mocked."""
    from ingest.pdf_to_md.cleaner import adaptive_cleanup
    from ingest.pdf_to_md.models import LegalDocumentProfile

    name = "Documento" + "a" * 42 + " de"
    digest = "1234567890" * 6 + "ab87"
    target = f"./{name}/assets/image_{digest}.png"
    suffix = "\n\n## Consideraciones\nFigura de prueba para el expediente.\n"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    pixels = (bytes(range(256)) * 977)[: 500 * 500]
    with Image.frombytes("L", (500, 500), pixels) as image:
        image.save(path)
    original_bytes = path.read_bytes()

    if representation == "angles":
        token = f"![Image](<{target}>)"
    elif representation == "quote":
        token = f"![Image]({quote(target, safe='/._-~')})"
    else:
        token = f"![Image]({target})"
    text = (
        token + suffix
        if position == "preamble"
        else "## Consideraciones\n\nFigura de prueba para el expediente.\n" + token + "\n"
    )

    result = adaptive_cleanup(text, LegalDocumentProfile(), tmp_path / "documento.md")

    assert token in result
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("indent", ["", "  ", "\t"])
@pytest.mark.parametrize(
    "token",
    [
        "![a](./assets/image_12345678901234567890abc87.png)",
        "![](./assets/image_12345678901234567890abc87.png)",
        "![a](<./Fallo marítimo/assets/image_12345678901234567890abc87.png>)",
        "![a](./Fallo%20mar%C3%ADtimo/assets/image_12345678901234567890abc87.png)",
        "![a](./Fallo marítimo/assets/image_12345678901234567890abc87.png)",
        "![#14 @figura](./assets/image_12345678901234567890abc87.png)",
        "![a](<./assets/1234567890#@.png>)",
        "![a](1234567890.png)\t![b](9876543210.png)",
    ],
)
def test_frontmatter_preserves_only_image_lines_verbatim(indent, token):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    source = f"{indent}{token}  \n\n## Consideraciones\nTexto jurídico.\n"
    assert strip_frontmatter_noise(source) == source.removesuffix("\n")


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("", True),
        ("Texto jurídico suficiente para la valoración.", True),
        ("abc123", True),
        ("abc1234", False),
        ("1234567890", False),
        ("TRIBUNAL ADMINISTRATIVO", False),
        ("abc", False),
        ("Contacto @tribunal", False),
        ("Texto con #referencia", False),
        ("![a]()", False),
        ("![a]( )", False),
        ("![a](\t)", False),
        ("![a](< >)", False),
        ("![a](<>)", False),
        ('![a](x.png "123")', False),
        ("![a](x.png '123')", False),
        ('![a](ruta.png "título")', True),
        ("![a](1234567890.png", False),
        ("![a](1234567890(87).png)", False),
        ("[a](1234567890.png)", False),
        ("`![a](1234567890.png)`", False),
        ("1234567890 ![a](x.png)", False),
        ("![a](x.png) @ruido", False),
        ("![a](1234567890.png) 1234567890", False),
        ("Figura del expediente ![a](./plano.png)", True),
    ],
)
def test_frontmatter_non_image_lines_keep_previous_decisions(line, kept):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    suffix = "\n\n## Consideraciones\nTexto jurídico."
    source = line + suffix
    assert strip_frontmatter_noise(source) == (source if kept else suffix[1:])


@pytest.mark.parametrize(
    "source",
    [
        "",
        "![a](1234567890.png)",
        "![a](1234567890.png)\nTexto sin encabezado.\n",
        "## Consideraciones\n![a](1234567890.png)\n",
        "![a](1234567890.png)\n## Consideraciones\n",
        "\n## Consideraciones\n![a](1234567890.png)\n",
    ],
)
def test_frontmatter_early_return_keeps_input_exactly(source):
    from ingest.pdf_to_md.text_cleanup import strip_frontmatter_noise

    assert strip_frontmatter_noise(source) == source


@pytest.mark.parametrize("control", [*range(32), *range(127, 160)])
@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("delimited", [False, True])
def test_c2_control_guard_preserves_all_control_destinations(
    tmp_path, control, absolute, delimited
):
    from ingest.pdf_to_md.images import relativize_image_refs

    directory = tmp_path.resolve()
    prefix = f"{directory}/" if absolute else "./"
    raw = f"{prefix}a {chr(control)}b.png"
    destination = f"<{raw}>" if delimited else raw
    source = f"Prosa ![a]({destination}) exterior."
    result = relativize_image_refs(source, directory / "documento.md")
    assert result == source
    assert relativize_image_refs(result, directory / "documento.md") == result


@pytest.mark.parametrize("control", [127, 128])
@pytest.mark.parametrize("delimited", [False, True])
def test_c2_control_guard_keeps_remainder_and_resumes_next_line(tmp_path, control, delimited):
    from ingest.pdf_to_md.images import relativize_image_refs

    directory = tmp_path.resolve()
    md_path = directory / "documento.md"
    raw = f"{directory}/a{chr(control)}b.png"
    destination = f"<{raw}>" if delimited else raw
    remainder = f" ![a]({destination}) luego ![b]({directory}/despues.png) fin.\n"
    source = f"Antes ![a]({directory}/antes.png)" + remainder
    source += f"Después ![c]({directory}/siguiente.png)."
    expected = "Antes ![a](./antes.png)" + remainder + "Después ![c](./siguiente.png)."
    result = relativize_image_refs(source, md_path)
    assert result == expected
    assert relativize_image_refs(result, md_path) == result


@pytest.mark.parametrize("name", ["a b.png", "á é.png", "Cafe\u0301.png", "a\u00a0b.png"])
@pytest.mark.parametrize("delimited", [False, True])
def test_c2_control_guard_keeps_printable_unicode_serialization(tmp_path, name, delimited):
    from ingest.pdf_to_md.images import relativize_image_refs

    directory = tmp_path.resolve()
    raw = str(directory / name)
    destination = f"<{raw}>" if delimited else raw
    source = f"Antes ![a]({destination}) después."
    expected = f"Antes ![a]({quote('./' + name, safe='/._-~')}) después."
    result = relativize_image_refs(source, directory / "documento.md")
    assert result == expected
    assert relativize_image_refs(result, directory / "documento.md") == result


@pytest.mark.parametrize("escape", ["%7F", "%80"])
@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("delimited", [False, True])
def test_c2_control_guard_does_not_decode_percent_sequences(tmp_path, escape, absolute, delimited):
    from ingest.pdf_to_md.images import relativize_image_refs

    directory = tmp_path.resolve()
    name = f"a{escape}b.png"
    raw = str(directory / name) if absolute else f"./{name}"
    destination = f"<{raw}>" if delimited else raw
    source = f"![a]({destination})"
    expected = f"![a]({quote('./' + name, safe='/._-~')})" if absolute else source
    result = relativize_image_refs(source, directory / "documento.md")
    assert result == expected
    assert relativize_image_refs(result, directory / "documento.md") == result
