import tempfile
import unittest
import zipfile
from pathlib import Path

from chess_coach.errors import IngestError
from chess_coach.ingest import (
    chunk_text,
    epub_to_text,
    ingest_book,
    read_source,
    slugify,
    split_sections,
    strip_gutenberg,
)
from chess_coach.knowledge import KnowledgeBase

PARA = "Control of the center is the first aim of the opening. " * 6  # ~330자

GUTENBERG = f"""The Project Gutenberg eBook of Chess Fundamentals
Some license text here.
*** START OF THE PROJECT GUTENBERG EBOOK CHESS FUNDAMENTALS ***

CHAPTER I

{PARA}

{PARA}

CHAPTER II

{PARA}
*** END OF THE PROJECT GUTENBERG EBOOK CHESS FUNDAMENTALS ***
Full license text that must not be indexed.
"""


def make_epub(path: Path):
    container = (
        '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c2"/><itemref idref="c1"/></spine></package>'
    )
    page = '<html><body><h1>{t}</h1><p>{p}</p><script>var x=1;</script></body></html>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/ch1.xhtml", page.format(t="Opening Play", p=PARA))
        z.writestr("OEBPS/ch2.xhtml", page.format(t="Endgames", p=PARA))


class TextProcessingTests(unittest.TestCase):
    def test_strip_gutenberg(self):
        t = strip_gutenberg(GUTENBERG)
        self.assertNotIn("license", t.lower())
        self.assertIn("CHAPTER I", t)

    def test_split_sections(self):
        sections = split_sections(strip_gutenberg(GUTENBERG))
        self.assertEqual([s for s, _ in sections], ["CHAPTER I", "CHAPTER II"])

    def test_markdown_headings(self):
        self.assertEqual([s for s, _ in split_sections("# 오프닝\n본문 하나\n\n## 엔드게임\n본문 둘")], ["오프닝", "엔드게임"])

    def test_chunk_text_respects_limit_and_drops_junk(self):
        chunks = chunk_text("\n\n".join([PARA] * 5 + ["42"]), max_chars=700)
        self.assertTrue(all(len(c) <= 910 for c in chunks))
        self.assertGreaterEqual(len(chunks), 2)
        self.assertNotIn("42", chunks)

    def test_chunk_text_splits_very_long_sentence(self):
        chunks = chunk_text("x" * 2500, max_chars=900)
        self.assertTrue(all(len(c) <= 900 for c in chunks))

    def test_hyphenation_removed(self):
        self.assertIn("development", chunk_text("The devel-\nopment of pieces matters a great deal in the opening phase.", min_chars=10)[0])

    def test_slugify(self):
        self.assertEqual(slugify("Chess Fundamentals!"), "chess-fundamentals")
        self.assertTrue(slugify("체스 기본기").startswith("book-"))


class IngestTests(unittest.TestCase):
    def test_epub_follows_spine_and_skips_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.epub"
            make_epub(p)
            text = epub_to_text(p)
            self.assertLess(text.index("Endgames"), text.index("Opening Play"))  # spine 순서
            self.assertNotIn("var x", text)

    def test_ingest_txt_and_load_back(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "cf.txt"
            src.write_text(GUTENBERG, encoding="utf-8")
            out, n = ingest_book(src, d, title="Chess Fundamentals", author="Capablanca", year="1921", phase="opening")
            self.assertEqual(out.name, "chess-fundamentals.jsonl")
            kb = KnowledgeBase.load(d, builtin=False)
            self.assertEqual(len(kb), n)
            c = kb.chunks[0]
            self.assertEqual(c.origin, "user")
            self.assertEqual(c.phase, "opening")
            self.assertEqual(c.source, "Capablanca, Chess Fundamentals (1921), CHAPTER I")
            self.assertTrue(all("license" not in x.text.lower() for x in kb.chunks))

    def test_reingest_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "a.txt"
            src.write_text(GUTENBERG, encoding="utf-8")
            _, n1 = ingest_book(src, d, title="T")
            _, n2 = ingest_book(src, d, title="T")
            self.assertEqual(n1, n2)
            self.assertEqual(len(KnowledgeBase.load(d, builtin=False)), n2)

    def test_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(IngestError):
                read_source(Path(d) / "missing.txt")
            bad = Path(d) / "x.docx"
            bad.write_text("x")
            with self.assertRaises(IngestError):
                read_source(bad)
            empty = Path(d) / "e.txt"
            empty.write_text("hi", encoding="utf-8")
            with self.assertRaises(IngestError):
                ingest_book(empty, d, title="E")
            with self.assertRaises(IngestError):
                ingest_book(empty, d, title="E", kind="opening")


if __name__ == "__main__":
    unittest.main()
