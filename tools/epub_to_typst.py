#!/usr/bin/env python3
"""Convert a simple, Calibre-generated EPUB into a readable Typst project."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attr(node: ET.Element, name: str, default: str = "") -> str:
    return node.attrib.get(name, default)


def escape_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    # These characters have meaning in Typst markup. The source book text is
    # otherwise emitted verbatim, with styling represented by HTML elements.
    for char in ("\\", "#", "$", "*", "_", "[", "]", "@"):
        value = value.replace(char, "\\" + char)
    return value


def clean_inline(value: str) -> str:
    return value.strip()


class Converter:
    def __init__(
        self, root: Path, output: Path, opf_path: Path, book_name: str
    ) -> None:
        self.root = root
        self.output = output
        self.opf_path = opf_path
        self.book_name = book_name
        self.images = output / "images"
        self.cover_name = ""

    def inline(self, node: ET.Element) -> str:
        tag = local_name(node.tag)
        classes = set(attr(node, "class").split())

        if tag == "br":
            return "\n"
        if tag == "img":
            source = attr(node, "src")
            filename = Path(unquote(urlsplit(source).path)).name
            return f'#image("images/{filename}", width: 100%)'

        pieces = [escape_text(node.text or "")]
        for child in list(node):
            pieces.append(self.inline(child))
            tail = escape_text(child.tail or "")
            # A styled content expression followed by `(` is parsed as a
            # function call by Typst. Keep the original typography while
            # separating those tokens syntactically.
            if tail.lstrip().startswith("("):
                pieces.append(f"#text[{tail}]")
            else:
                pieces.append(tail)
        body = "".join(pieces)

        if tag == "sup":
            return f"#super[{body}]"
        if tag == "sub":
            return f"#sub[{body}]"
        if tag in {"em", "i"} or classes & {"ePub-I"}:
            return f"#emph[{body}]"
        if tag in {"strong", "b"} or classes & {"ePub-B"}:
            return f"#strong[{body}]"
        if classes & {"ePub-BI"}:
            return f"#emph[#strong[{body}]]"
        if classes & {"ePub-SC", "ePub-SC1", "ePub-SC2", "ePub-SC-B"}:
            return f'#text(font: "LMRomanCaps10")[{body}]'
        return body

    def block_body(self, node: ET.Element) -> str:
        return clean_inline(self.inline(node))

    def heading(self, level: int, body: str) -> str:
        if not body:
            return ""
        return f"{'=' * level} {body}\n\n"

    def paragraph(self, node: ET.Element) -> str:
        classes = set(attr(node, "class").split())
        body = self.block_body(node)
        if not body:
            return ""
        if classes & {"sp", "sp1"}:
            return ""
        if classes & {"TIT"}:
            return f'#align(center)[#text(size: 22pt, weight: "bold")[{body}]]\n\n'
        if classes & {"STIT"}:
            return f"#align(center)[#text(size: 13pt)[{body}]]\n\n"
        if classes & {"AU", "PUB"}:
            return f"#align(center)[{body}]\n\n"
        if classes & {"caption", "figcaption", "figure-caption", "image-caption"}:
            return f"#align(center)[#text(size: 9pt)[{body}]]\n\n"
        if classes & {"CN"}:
            return f'#align(center)[#text(size: 11pt, fill: rgb("8c2f39"))[CHAPTER {body}]]\n'
        if classes & {"CT"}:
            return self.heading(1, body)
        if classes & {"FMH", "BMH"}:
            return f"#pagebreak()\n{self.heading(1, body)}"
        if classes & {"BMH1", "BIB"}:
            return self.heading(2, body)
        if classes & {"DED", "CIT", "CRT", "CRT-LS", "EX", "EXI", "EX1", "EX1O-ind"}:
            return f"#block(inset: (left: 1.5em, right: 1.5em))[#align(center)[{body}]]\n\n"
        if classes & {"CO"}:
            return f"#par(first-line-indent: 4em)[{body}]\n\n"
        if classes & {"LIST", "LIST1", "LIST2", "BL", "BL1", "BL2"}:
            return f"#block(inset: (left: 1.4em))[#par(first-line-indent: 0pt)[{body}]]\n\n"
        if classes & {"BIB1", "IN", "INA", "R", "NTX"}:
            return f"#text(size: 9pt)[{body}]\n\n"
        if classes & {"RIH"}:
            return f"#par(first-line-indent: 0pt, spacing: 0.45em)[{body}]\n\n"
        return f"{body}\n\n"

    def element(self, node: ET.Element) -> str:
        tag = local_name(node.tag)
        classes = set(attr(node, "class").split())
        if tag in {"p", "div"}:
            if "h1-top" in classes or "ex-top" in classes:
                return ""
            if "img" in classes:
                return self.block_body(node) + "\n\n"
            return self.paragraph(node)
        if tag == "h1":
            return f"#pagebreak()\n{self.heading(2, self.block_body(node))}"
        if tag == "h2":
            return self.heading(3, self.block_body(node))
        if tag == "h3":
            return self.heading(3, self.block_body(node))
        if tag in {"ul", "ol"}:
            return self.block_body(node) + "\n\n"
        if tag == "blockquote":
            return f"#block(inset: (left: 1.5em, right: 1.5em))[#emph[{self.block_body(node)}]]\n\n"
        return ""

    def document(self, path: Path) -> str:
        tree = ET.parse(path)
        body = next(
            (node for node in tree.iter() if local_name(node.tag) == "body"), None
        )
        if body is None:
            return ""
        return "".join(self.element(node) for node in list(body))

    def copy_images(self) -> None:
        self.images.mkdir(parents=True, exist_ok=True)
        image_types = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
        for source in self.root.rglob("*"):
            if source.suffix.lower() not in image_types:
                continue
            if source.is_file():
                shutil.copy2(source, self.images / source.name)

    def manifest(self) -> dict[str, str]:
        opf = ET.parse(self.opf_path).getroot()
        return {
            attr(item, "id"): attr(item, "href")
            for item in opf.findall("opf:manifest/opf:item", NS)
        }

    def find_cover(self) -> str:
        opf = ET.parse(self.opf_path).getroot()
        manifest = self.manifest()
        cover_id = ""
        for node in opf.iter():
            if local_name(node.tag) == "meta" and attr(node, "name") == "cover":
                cover_id = attr(node, "content")
                break
        href = manifest.get(cover_id, "")
        if href:
            return Path(unquote(urlsplit(href).path)).name
        for path in sorted(self.images.iterdir()):
            if "cover" in path.stem.lower():
                return path.name
        return ""

    def spine_paths(self) -> list[Path]:
        opf = ET.parse(self.opf_path).getroot()
        manifest = self.manifest()
        result = []
        for itemref in opf.findall("opf:spine/opf:itemref", NS):
            href = manifest.get(attr(itemref, "idref"))
            if href:
                href = unquote(urlsplit(href).path)
                result.append((self.opf_path.parent / href).resolve())
        return result

    def render(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        self.copy_images()
        self.cover_name = self.find_cover()
        files = self.spine_paths()
        source = [
            '#set page(paper: "a6", margin: (top: 12mm, bottom: 13mm, left: 12mm, right: 12mm), fill: rgb("fbf8f2"))',
            '#set text(font: ("LMRoman10", "Source Han Serif"), size: 10.2pt, fill: rgb("25231f"), lang: "en")',
            "#set par(justify: true, leading: 0.63em, spacing: 0.52em, first-line-indent: 1em)",
            "#set heading(numbering: none)",
            "#show heading.where(level: 1): set align(center)",
            '#show heading.where(level: 1): set text(size: 16pt, weight: "bold", fill: rgb("8c2f39"))',
            '#show heading.where(level: 2): set text(size: 12pt, weight: "bold", fill: rgb("8c2f39"))',
            '#show heading.where(level: 3): set text(size: 10.8pt, weight: "bold", fill: rgb("8c2f39"))',
            '#set page(footer: context { align(center)[#text(size: 8pt, fill: rgb("6f665d"))[— #counter(page).display() —]] })',
            '#show math.equation: set text(font: "New Computer Modern Math")',
            "",
        ]
        if self.cover_name:
            source.extend(
                [
                    f'#align(center)[#image("images/{self.cover_name}", width: 100%)]',
                    "#pagebreak()",
                ]
            )
        for path in files:
            if path.name == "titlepage.xhtml":
                continue
            if path.name == "part0004.html":
                source.extend(
                    [
                        "#pagebreak()",
                        "= Contents",
                        "#outline(title: none, depth: 3)",
                        "",
                    ]
                )
                continue
            source.append(self.document(path))
        output = self.output / f"{self.book_name}.typ"
        output.write_text("\n".join(source), encoding="utf-8")
        return output


def typst_stem(epub: Path) -> str:
    """Turn an EPUB filename into a readable, shell-friendly Typst stem."""
    stem = re.sub(r"[^\w.-]+", "-", epub.stem, flags=re.UNICODE)
    stem = re.sub(r"-{2,}", "-", stem).strip("-.")
    return stem or "book"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("epub", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="epub-to-typst-") as temp:
        work = Path(temp)
        shutil.unpack_archive(args.epub, work, "zip")
        container = work / "META-INF" / "container.xml"
        opf_path = None
        if container.exists():
            container_root = ET.parse(container).getroot()
            rootfile = next(
                (
                    node
                    for node in container_root.iter()
                    if local_name(node.tag) == "rootfile"
                ),
                None,
            )
            if rootfile is not None:
                opf_path = work / unquote(attr(rootfile, "full-path"))
        if opf_path is None or not opf_path.exists():
            candidates = sorted(work.rglob("*.opf"))
            if not candidates:
                raise FileNotFoundError("EPUB package document (*.opf) was not found")
            opf_path = candidates[0]
        result = Converter(
            opf_path.parent,
            args.output,
            opf_path,
            typst_stem(args.epub),
        ).render()
        print(result)


if __name__ == "__main__":
    main()
