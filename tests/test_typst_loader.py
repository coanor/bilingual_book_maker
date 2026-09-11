import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from book_maker.loader.typst_loader import TypstBookLoader

REPO = Path(__file__).resolve().parent.parent
HERMETIC = Path(__file__).resolve().parent / "hermetic"


class MappingModel:
    instances = []

    def __init__(
        self,
        key,
        language,
        api_base=None,
        temperature=1.0,
        source_lang="auto",
        **kwargs,
    ):
        self.calls = []
        MappingModel.instances.append(self)

    def translate_list(self, texts):
        self.calls.append(list(texts))
        replacements = {
            "Chapter One": "第一章",
            "A ": "一个",
            "styled": "有样式的",
            " paragraph.": "段落。",
            "paragraph.": "段落。",
            "caption.": "说明文字。",
            "First line.\nSecond line.": "第一行。\n第二行。",
        }
        translated = []
        for text in texts:
            for source, target in replacements.items():
                text = text.replace(source, target)
            translated.append(text)
        return translated


class DroppingMarkerModel(MappingModel):
    def translate_list(self, texts):
        translated = super().translate_list(texts)
        return [text.replace("@@BBM_TYPST_PROTECT_0@@", "") for text in translated]


class BatchDroppingMarkerModel(MappingModel):
    def translate_list(self, texts):
        translated = super().translate_list(texts)
        if len(texts) > 1:
            return [text.replace("@@BBM_TYPST_PROTECT_0@@", "") for text in translated]
        return translated


class InventingMarkerOnceModel(MappingModel):
    def translate_list(self, texts):
        translated = super().translate_list(texts)
        if len(self.calls) == 1:
            return [f"{text}@@hallucinated marker@@" for text in translated]
        return translated


class BrokenFragmentModel(DroppingMarkerModel):
    def translate_list(self, texts):
        translated = super().translate_list(texts)
        if len(texts) > 1 and not any("@@BBM_TYPST_PROTECT_" in text for text in texts):
            return translated[:-1]
        return translated


class InterruptingModel(MappingModel):
    def translate_list(self, texts):
        self.calls.append(list(texts))
        if any("Second paragraph." in text for text in texts):
            raise KeyboardInterrupt
        return [text.replace("First paragraph.", "第一段。") for text in texts]


def make_loader(path, model=MappingModel, *, single_translate=False, resume=False):
    return TypstBookLoader(
        str(path),
        model,
        key="",
        resume=resume,
        language="Simplified Chinese",
        single_translate=single_translate,
    )


def test_typst_loader_translates_prose_without_changing_layout_code(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        "\n".join(
            [
                '#set page(paper: "a6")',
                '#set text(font: "LMRoman10", size: 10pt)',
                "#show heading: set text(fill: red)",
                "",
                "= Chapter One",
                "",
                "A #emph[styled] paragraph.",
                "",
                '#align(center)[#image("images/figure.jpg", width: 100%)]',
                "",
                "#align(center)[#text(size: 9pt)[A caption.]]",
            ]
        ),
        encoding="utf-8",
    )

    make_loader(book).make_bilingual_book()

    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert output.count('#set page(paper: "a6")') == 1
    assert output.count('#set text(font: "LMRoman10", size: 10pt)') == 1
    assert output.count("#show heading: set text(fill: red)") == 1
    assert output.count('#image("images/figure.jpg", width: 100%)') == 1
    assert "= Chapter One\n\n= 第一章" in output
    assert "A #emph[styled] paragraph." in output
    assert "一个#emph[有样式的]段落。" in output
    assert "#align(center)[#text(size: 9pt)[A caption.]]" in output
    assert "#align(center)[#text(size: 9pt)[一个说明文字。]]" in output

    sent = "\n".join(text for call in MappingModel.instances[-1].calls for text in call)
    assert "#set" not in sent
    assert "#image" not in sent
    assert "#emph" not in sent


def test_typst_loader_single_translation_keeps_styles_without_source_text(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        '#set text(font: "LMRoman10")\n\n= Chapter One\n\nA paragraph.\n',
        encoding="utf-8",
    )

    make_loader(book, single_translate=True).make_bilingual_book()

    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert output.count('#set text(font: "LMRoman10")') == 1
    assert "Chapter One" not in output
    assert "A paragraph." not in output
    assert "= 第一章" in output
    assert "一个段落。" in output


def test_cli_accepts_typst_books(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        '#set text(font: "LMRoman10")\n\nText to translate.\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(HERMETIC), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    process = subprocess.run(
        [
            sys.executable,
            "make_book.py",
            "--book_name",
            str(book),
            "--api_format",
            "google",
            "--test",
            "--test_num",
            "1",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    output = tmp_path / "book_bilingual.typ"
    assert output.exists()
    assert output.read_text(encoding="utf-8").count("LMRoman10") == 1
    assert f"Bilingual book saved: {output.resolve()}" in process.stdout


def test_typst_loader_translates_internal_line_breaks_as_one_paragraph(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        "#pagebreak()\n= Chapter One\n\nFirst line.\nSecond line.\n",
        encoding="utf-8",
    )

    make_loader(book).make_bilingual_book()

    calls = MappingModel.instances[-1].calls
    sent_items = [text for call in calls for text in call]
    assert any("First line.\nSecond line." in text for text in sent_items)
    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert output.count("#pagebreak()") == 1
    assert "First line.\nSecond line.\n\n第一行。\n第二行。" in output


def test_typst_loader_recovers_when_translation_drops_syntax_markers(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text("A #emph[styled] paragraph.\n", encoding="utf-8")

    make_loader(book, DroppingMarkerModel).make_bilingual_book()

    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert "A #emph[styled] paragraph." in output
    assert "一个#emph[有样式的]段落。" in output
    assert not (tmp_path / "book_bilingual_temp.typ").exists()


def test_typst_loader_retries_marker_failure_as_single_paragraph(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        "A #emph[styled] paragraph.\n\nA #emph[styled] paragraph.\n",
        encoding="utf-8",
    )
    loader = make_loader(book, BatchDroppingMarkerModel)
    loader.batch_size = 2

    loader.make_bilingual_book()

    calls = BatchDroppingMarkerModel.instances[-1].calls
    assert [len(call) for call in calls] == [2, 1, 1]
    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert output.count("一个#emph[有样式的]段落。") == 2


def test_typst_loader_retries_a_translation_that_invents_a_marker(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text("A paragraph.\n", encoding="utf-8")

    make_loader(book, InventingMarkerOnceModel).make_bilingual_book()

    calls = InventingMarkerOnceModel.instances[-1].calls
    assert [len(call) for call in calls] == [1, 1]
    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert "一个段落。" in output
    assert "@@" not in output


def test_typst_loader_retranslates_a_cached_invented_marker(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text("A paragraph.\n", encoding="utf-8")
    (tmp_path / ".book.temp.bin").write_text(
        json.dumps([["一個@@hallucinated marker@@段落。"]], ensure_ascii=False),
        encoding="utf-8",
    )

    make_loader(book, MappingModel, resume=True).make_bilingual_book()

    calls = MappingModel.instances[-1].calls
    assert [len(call) for call in calls] == [1]
    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert "一个段落。" in output
    assert "@@" not in output


def test_typst_loader_still_stops_when_fragment_reassembly_is_ambiguous(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text("A #emph[styled] paragraph.\n", encoding="utf-8")

    with pytest.raises(Exception, match="Something is wrong when translating"):
        make_loader(book, BrokenFragmentModel).make_bilingual_book()

    assert not (tmp_path / "book_bilingual.typ").exists()
    temporary = (tmp_path / "book_bilingual_temp.typ").read_text(encoding="utf-8")
    assert temporary.strip() == "A #emph[styled] paragraph."


def test_typst_loader_resumes_without_translating_finished_paragraphs_again(tmp_path):
    book = tmp_path / "book.typ"
    book.write_text(
        "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n",
        encoding="utf-8",
    )

    interrupted = make_loader(book, InterruptingModel)
    interrupted.batch_size = 1
    with pytest.raises(SystemExit) as exit_info:
        interrupted.make_bilingual_book()
    assert exit_info.value.code == 0

    resumed = make_loader(book, MappingModel, resume=True)
    resumed.batch_size = 1
    resumed.make_bilingual_book()

    calls = MappingModel.instances[-1].calls
    assert all("First paragraph." not in text for call in calls for text in call)
    output = (tmp_path / "book_bilingual.typ").read_text(encoding="utf-8")
    assert output.count("第一段。") == 1
    assert output.count("First paragraph.") == 1
