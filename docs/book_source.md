# Translate from Different Sources

## txt/srt
Txt files and srt files are plain text files. This program can translate plain text.

    python3 make_book.py --book_name test_books/the_little_prince.txt --test --language zh-hans

## markdown
Markdown files can be translated directly with `--book_name your_doc.md`; use `--prompt prompt_md.json` for the Markdown-specific prompt.

    python3 make_book.py --book_name your_doc.md --key ${openai_key} --model gpt-5-mini --prompt prompt_md.json

PromptDown `.md` files go to `--prompt`; Markdown books go to `--book_name`.

## typst
Typst `.typ` books can be translated directly. Layout directives such as `#set`, `#show`,
`#image`, page breaks, fonts, and styled content wrappers are protected; prose inside the
wrappers is translated. The output is written beside the source as `*_bilingual.typ`.

    python3 make_book.py --book_name your_book.typ --api_format codex --language zh-hans

To convert an EPUB before translating it, use the bundled converter. It produces an A6
Typst project and copies image resources into the output directory.

    python3 tools/epub_to_typst.py your_book.epub typst-output

## epub
epub is made of html files. By default, we only translate contents in `<p>`. Use `--translate-tags` to specify tags need for translation. Use comma to separate multiple tags. For example: `--translate-tags h1,h2,h3,p,div`

    bbook_maker --book_name test_books/animal_farm.epub --key ${openai_key} --model gpt-5-mini --translate-tags div,p

If you want to translate strings in an e-book that aren't labeled with any tags, you can use the `--allow_navigable_strings` parameter. This will add the strings to the translation queue. <br>
**Note that it's best to look for e-books that are more standardized if possible.**
