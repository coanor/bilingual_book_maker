from book_maker.loader.epub_loader import EPUBBookLoader
from book_maker.loader.txt_loader import TXTBookLoader
from book_maker.loader.srt_loader import SRTBookLoader
from book_maker.loader.md_loader import MarkdownBookLoader
from book_maker.loader.pdf_loader import PDFBookLoader
from book_maker.loader.typst_loader import TypstBookLoader

BOOK_LOADER_DICT = {
    "epub": EPUBBookLoader,
    "txt": TXTBookLoader,
    "srt": SRTBookLoader,
    "md": MarkdownBookLoader,
    "pdf": PDFBookLoader,
    "typ": TypstBookLoader,
    # TODO add more here
}
