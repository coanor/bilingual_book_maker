import re
import sys
from pathlib import Path

from rich import print

from .md_loader import MarkdownBookLoader


class TypstBookLoader(MarkdownBookLoader):
    """Translate prose in Typst source while leaving layout code untouched."""

    _NON_TEXT_PREFIXES = (
        "#set ",
        "#show ",
        "#let ",
        "#import ",
        "#include ",
        "#metadata(",
    )

    def process_markdown_content(self):
        self.md_blocks = []
        for lines, raw in self._source_blocks(self.origin_book):
            if raw:
                self._append_block(lines, translatable=False)
                continue

            flags = [self._has_translatable_text(line) for line in lines]
            group = []
            group_flag = flags[0]
            for line, flag in zip(lines, flags):
                if group and flag != group_flag:
                    self._append_block(group, translatable=group_flag)
                    group = []
                group.append(line)
                group_flag = flag
            if group:
                self._append_block(group, translatable=group_flag)

    @classmethod
    def _source_blocks(cls, lines):
        blocks = []
        block = []
        in_raw_block = False
        raw_marker = ""

        for line in lines:
            stripped = line.strip()
            marker = cls._raw_fence(stripped)
            if in_raw_block:
                block.append(line)
                if marker == raw_marker:
                    blocks.append((block, True))
                    block = []
                    in_raw_block = False
                    raw_marker = ""
                continue
            if marker:
                if block:
                    blocks.append((block, False))
                block = [line]
                in_raw_block = True
                raw_marker = marker
                continue
            if not stripped:
                if block:
                    blocks.append((block, False))
                    block = []
                continue
            block.append(line)

        if block:
            blocks.append((block, in_raw_block))
        return blocks

    @staticmethod
    def _raw_fence(stripped):
        match = re.match(r"^(`{3,})", stripped)
        return match.group(1) if match else ""

    def _has_translatable_text(self, line):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith(self._NON_TEXT_PREFIXES):
            return False
        protected, replacements = self._protect_inline_markdown(line)
        visible = protected
        for token in replacements:
            visible = visible.replace(token, "")
        return any(char.isalpha() for char in visible)

    @staticmethod
    def _protect_inline_markdown(text):
        replacements = {}

        def protect(fragment):
            token = f"@@BBM_TYPST_PROTECT_{len(replacements)}@@"
            replacements[token] = fragment
            return token

        output = []
        index = 0
        heading = re.match(r"^=+[ \t]+", text)
        if heading:
            output.append(protect(heading.group(0)))
            index = heading.end()

        while index < len(text):
            char = text[index]
            if char == "\\" and index + 1 < len(text):
                output.append(protect(text[index : index + 2]))
                index += 2
                continue
            if char == "#":
                end = TypstBookLoader._command_end(text, index)
                if end > index + 1:
                    output.append(protect(text[index:end]))
                    index = end
                    continue
            if char in "[]{}":
                output.append(protect(char))
                index += 1
                continue
            if char == "`":
                end = TypstBookLoader._raw_end(text, index)
                output.append(protect(text[index:end]))
                index = end
                continue
            if char == "@":
                label = re.match(r"@[A-Za-z0-9_:.+-]+", text[index:])
                if label:
                    output.append(protect(label.group(0)))
                    index += len(label.group(0))
                    continue
            output.append(char)
            index += 1

        return "".join(output), replacements

    @staticmethod
    def _command_end(text, start):
        index = start + 1
        identifier = re.match(r"[A-Za-z_][A-Za-z0-9_-]*", text[index:])
        if not identifier:
            return start + 1
        index += len(identifier.group(0))

        while index < len(text):
            if text[index] == "(":
                index = TypstBookLoader._balanced_end(text, index, "(", ")")
                continue
            if text[index] == ".":
                member = re.match(r"\.[A-Za-z_][A-Za-z0-9_-]*", text[index:])
                if not member:
                    break
                index += len(member.group(0))
                continue
            break

        if index < len(text) and text[index] == "[":
            index += 1
        return index

    @staticmethod
    def _balanced_end(text, start, opening, closing):
        depth = 0
        quote = ""
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return index + 1
        return len(text)

    @staticmethod
    def _raw_end(text, start):
        marker = re.match(r"`+", text[start:]).group(0)
        end = text.find(marker, start + len(marker))
        return len(text) if end < 0 else end + len(marker)

    @staticmethod
    def _restore_inline_markdown(text, replacements):
        for token, original in replacements.items():
            if text.count(token) != 1:
                raise ValueError(f"Translation did not preserve Typst marker {token}")
            text = text.replace(token, original)
        return text

    @staticmethod
    def _is_heading(text):
        return bool(re.match(r"^=+[ \t]+\S", text.strip()))

    @staticmethod
    def _heading_level(text):
        return len(re.match(r"^(=+)", text.strip()).group(1))

    @staticmethod
    def _heading_label(text):
        return re.sub(r"^=+[ \t]+", "", text.strip()).strip()

    def _with_breadcrumb_context(self, breadcrumb, translate, translator=None):
        translator = translator if translator is not None else self.translate_model
        if not self.context_flag or not breadcrumb:
            return translate()
        if not getattr(translator, "context_flag", False):
            return translate()

        context_list = getattr(translator, "context_list", None)
        translated_list = getattr(translator, "context_translated_list", None)
        if not isinstance(context_list, list) or not isinstance(translated_list, list):
            return translate()

        context_marker = f"Typst section context: {breadcrumb}"
        translated_marker = "Context acknowledged."
        context_list.append(context_marker)
        translated_list.append(translated_marker)
        try:
            return translate()
        finally:
            if context_marker in context_list:
                context_list.remove(context_marker)
            if translated_marker in translated_list:
                translated_list.remove(translated_marker)

    def make_bilingual_book(self):
        try:
            self.bilingual_result = self._render_bilingual_result(
                translate_missing=True
            )
            out_path = Path(self.md_name).with_name(
                f"{Path(self.md_name).stem}_bilingual.typ"
            )
            self.save_file(out_path, self.bilingual_result)
            self.announce_saved_book(out_path)
        except KeyboardInterrupt:
            print("Interrupted. Saving progress so you can resume later.")
            self._save_progress()
            self._save_temp_book()
            sys.exit(0)
        except Exception as error:
            print(f"Error: {error}")
            print("Saving progress so you can resume later.")
            self._save_progress()
            self._save_temp_book()
            raise

    def _save_temp_book(self):
        self.bilingual_temp_result = self._render_bilingual_result(
            translate_missing=False
        )
        temp_path = Path(self.md_name).with_name(
            f"{Path(self.md_name).stem}_bilingual_temp.typ"
        )
        self.save_file(temp_path, self.bilingual_temp_result)

    @staticmethod
    def save_file(book_path, content):
        try:
            with open(book_path, "w", encoding="utf-8") as file:
                file.write("\n\n".join(content).rstrip() + "\n")
        except Exception as error:
            raise Exception("can not save file") from error
