#!/usr/bin/env python3
"""Turn BBM's alternating Typst output into a side-by-side edition."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from book_maker.loader.typst_loader import TypstBookLoader

LAYOUT_PREAMBLE = """#set page(
  paper: "a5",
  flipped: true,
  margin: (top: 10mm, bottom: 11mm, left: 11mm, right: 11mm),
)

#let bbm_pair(source, translation) = grid(
  columns: (1fr, 1fr),
  column-gutter: 6mm,
  align: top,
  source,
  translation,
)"""

_BLOCK_SEPARATOR_RE = re.compile(r"\n[ \t]*\n+")


@dataclass(frozen=True)
class LayoutItem:
    source: str
    translation: str | None = None


def _source_blocks(path: Path):
    parser = TypstBookLoader.__new__(TypstBookLoader)
    parser.origin_book = path.read_text(encoding="utf-8").splitlines()
    parser.md_blocks = []
    parser.process_markdown_content()
    return parser.md_blocks


def _rendered_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").strip()
    return [block.strip("\n") for block in _BLOCK_SEPARATOR_RE.split(text) if block]


def align_bilingual_blocks(original: Path, bilingual: Path) -> list[LayoutItem]:
    """Recover source/translation pairs from BBM's alternating output."""
    source_blocks = _source_blocks(original)
    rendered = _rendered_blocks(bilingual)
    items = []
    cursor = 0

    for index, block in enumerate(source_blocks):
        if cursor >= len(rendered) or rendered[cursor] != block.text:
            found = rendered[cursor][:80] if cursor < len(rendered) else "<end of file>"
            raise ValueError(
                f"Cannot align source block {index + 1}; bilingual file has {found!r}"
            )
        cursor += 1

        translatable = block.translatable and not TypstBookLoader._is_special_text(
            block.text
        )
        if not translatable:
            items.append(LayoutItem(block.text))
            continue

        if index + 1 < len(source_blocks):
            next_source = source_blocks[index + 1].text
            next_cursor = next(
                (
                    position
                    for position in range(cursor + 1, len(rendered))
                    if rendered[position] == next_source
                ),
                None,
            )
            if next_cursor is None:
                raise ValueError(
                    f"Cannot align source block {index + 1}; the next source "
                    "block was not found after its translation"
                )
        else:
            next_cursor = len(rendered)

        translation_blocks = rendered[cursor:next_cursor]
        if not translation_blocks:
            raise ValueError(
                f"Cannot align source block {index + 1}; its translation is missing"
            )
        items.append(LayoutItem(block.text, "\n\n".join(translation_blocks)))
        cursor = next_cursor

    if cursor != len(rendered):
        raise ValueError(
            f"Cannot align bilingual file; {len(rendered) - cursor} extra block(s) remain"
        )
    return items


def _pair(source: str, translation: str) -> str:
    return f"#bbm_pair(\n[\n{source}\n],\n[\n{translation}\n],\n)"


def render_side_by_side(items: list[LayoutItem]) -> str:
    rendered = []
    inserted_preamble = False

    for item in items:
        block = (
            item.source
            if item.translation is None
            else _pair(item.source, item.translation)
        )
        rendered.append(block)
        if (
            not inserted_preamble
            and item.translation is None
            and "#set page(" in item.source
        ):
            rendered.append(LAYOUT_PREAMBLE)
            inserted_preamble = True

    if not inserted_preamble:
        rendered.insert(0, LAYOUT_PREAMBLE)
    return "\n\n".join(rendered).rstrip() + "\n"


def convert_side_by_side(original: Path, bilingual: Path, output: Path) -> Path:
    original = Path(original)
    bilingual = Path(bilingual)
    output = Path(output)
    items = align_bilingual_blocks(original, bilingual)
    output.write_text(render_side_by_side(items), encoding="utf-8")
    return output


def _default_original(bilingual: Path) -> Path:
    suffix = "_bilingual"
    if not bilingual.stem.endswith(suffix):
        raise ValueError(
            "Use --original when the input name does not end in _bilingual.typ"
        )
    return bilingual.with_name(bilingual.stem.removesuffix(suffix) + bilingual.suffix)


def _default_output(bilingual: Path) -> Path:
    return bilingual.with_name(f"{bilingual.stem}_side_by_side{bilingual.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a completed BBM Typst translation to an A5 landscape side-by-side edition."
    )
    parser.add_argument("bilingual", type=Path, help="completed *_bilingual.typ file")
    parser.add_argument("--original", type=Path, help="original Typst source")
    parser.add_argument("--output", type=Path, help="new side-by-side Typst file")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing output file"
    )
    args = parser.parse_args()

    original = args.original or _default_original(args.bilingual)
    output = args.output or _default_output(args.bilingual)
    if output.exists() and not args.force:
        parser.error(f"output already exists: {output} (pass --force to replace it)")
    if output.parent.resolve() != args.bilingual.parent.resolve():
        parser.error(
            "output must stay beside the bilingual file so relative assets work"
        )

    try:
        result = convert_side_by_side(original, args.bilingual, output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
