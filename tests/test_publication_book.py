"""Protect exact-size vector embedding and readable caption failures."""
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from americas_markov.publication_book import build_book, _figure_page


class PublicationBookTests(unittest.TestCase):
    def _master(self, root, width=160, height=185):
        path=root/"Figure_01_master.pdf"
        c=canvas.Canvas(str(path),pagesize=(width*mm,height*mm))
        c.setFont("Helvetica",8); c.drawString(10*mm,10*mm,"Vector figure text")
        c.save()
        return {"id":"Figure_01","stem":"Figure_01","title":"Observed classification",
                "caption":"Observed on 1 January 2023. Unknown classifications remain visible.",
                "source":"Frozen source data.","width_mm":160,"height_mm":185,"role":"main"}

    def test_vector_text_survives_exact_size_book(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);item=self._master(root)
            out=build_book(root,[item],[])
            pages=PdfReader(out).pages
            self.assertEqual(len(pages),2)
            text=pages[1].extract_text()
            self.assertIn("Vector figure text",text)
            self.assertIn("1 January 2023",text)
            self.assertAlmostEqual(float(pages[1].mediabox.width)/mm,210,places=2)

    def test_rejects_mismatched_master_size(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);item=self._master(root,width=159)
            with self.assertRaisesRegex(ValueError,"master size"):
                _figure_page(root,item)

    def test_long_caption_is_not_truncated_or_shrunk(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);item=self._master(root)
            item["caption"]="The source classification is observed. "*200
            with self.assertRaisesRegex(ValueError,"caption exceeds"):
                _figure_page(root,item)


if __name__=="__main__":unittest.main()
