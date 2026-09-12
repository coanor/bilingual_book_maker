import subprocess

import pytest

from tools.typst_side_by_side import convert_side_by_side


def test_converts_bbm_pairs_and_keeps_layout_blocks_full_width(tmp_path):
    original = tmp_path / "book.typ"
    bilingual = tmp_path / "book_bilingual.typ"
    output = tmp_path / "book_side_by_side.typ"
    original.write_text(
        "\n".join(
            [
                '#set page(paper: "a6")',
                "#set text(size: 10pt)",
                "",
                "= Chapter One",
                "",
                "A #emph[styled] paragraph.",
                "",
                '#image("figure.png", width: 100%)',
            ]
        ),
        encoding="utf-8",
    )
    bilingual.write_text(
        "\n\n".join(
            [
                '#set page(paper: "a6")\n#set text(size: 10pt)',
                "= Chapter One",
                "= 第一章",
                "A #emph[styled] paragraph.",
                "一個#emph[有樣式的]段落。",
                '#image("figure.png", width: 100%)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    convert_side_by_side(original, bilingual, output)

    rendered = output.read_text(encoding="utf-8")
    assert rendered.count("#bbm_pair(") == 2
    assert '#image("figure.png", width: 100%)' in rendered
    assert rendered.count('#image("figure.png", width: 100%)') == 1
    assert 'paper: "a5"' in rendered
    assert "flipped: true" in rendered
    assert "= Chapter One\n],\n[\n= 第一章" in rendered


def test_rejects_a_bilingual_file_that_cannot_be_aligned(tmp_path):
    original = tmp_path / "book.typ"
    bilingual = tmp_path / "book_bilingual.typ"
    output = tmp_path / "book_side_by_side.typ"
    original.write_text("One.\n\nTwo.\n", encoding="utf-8")
    bilingual.write_text("One.\n\n一。\n", encoding="utf-8")

    with pytest.raises(ValueError, match="align"):
        convert_side_by_side(original, bilingual, output)


def test_keeps_multiple_translation_paragraphs_with_their_source(tmp_path):
    original = tmp_path / "book.typ"
    bilingual = tmp_path / "book_bilingual.typ"
    output = tmp_path / "book_side_by_side.typ"
    original.write_text("One long paragraph.\n\nNext paragraph.\n", encoding="utf-8")
    bilingual.write_text(
        "One long paragraph.\n\n"
        "譯文的第一段。\n\n"
        "譯文的第二段。\n\n"
        "Next paragraph.\n\n"
        "下一段。\n",
        encoding="utf-8",
    )

    convert_side_by_side(original, bilingual, output)

    rendered = output.read_text(encoding="utf-8")
    assert rendered.count("#bbm_pair(") == 2
    assert "譯文的第一段。\n\n譯文的第二段。" in rendered


def test_generated_source_compiles_with_typst(tmp_path):
    original = tmp_path / "book.typ"
    bilingual = tmp_path / "book_bilingual.typ"
    output = tmp_path / "book_side_by_side.typ"
    original.write_text(
        '#set page(paper: "a6")\n\nA #emph[styled] paragraph.\n',
        encoding="utf-8",
    )
    bilingual.write_text(
        '#set page(paper: "a6")\n\n'
        "A #emph[styled] paragraph.\n\n"
        "一個#emph[有樣式的]段落。\n",
        encoding="utf-8",
    )
    convert_side_by_side(original, bilingual, output)

    result = subprocess.run(
        ["typst", "compile", str(output), str(tmp_path / "book.pdf")],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "book.pdf").exists()
