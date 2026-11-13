import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymupdf
from pdf_text import page_text

class PdfTextTests(unittest.TestCase):
    def test_characters_reading_order_and_rotation(self):
        with pymupdf.open() as doc:
            page=doc.new_page(width=600,height=800)
            page.insert_text((50,100),'First line\nSecond line',fontsize=12)
            page.insert_text((350,100),'Right column',fontsize=12)
            data=page_text(page)
            text='\n\n'.join('\n'.join(''.join(c[0] for c in line) for line in block) for block in data['blocks'])
            self.assertEqual(text,'First line\nSecond line\n\nRight column')
            self.assertEqual((data['width'],data['height']),(600,800))
            first=data['blocks'][0][0][0]
            self.assertEqual(first[0],'F');self.assertEqual(first[1],50)
            page.set_rotation(90)
            rotated=page_text(page)
            self.assertEqual((rotated['width'],rotated['height']),(800,600))
            expected=pymupdf.Rect(first[1:])*page.rotation_matrix
            for actual,value in zip(rotated['blocks'][0][0][0][1:],expected):self.assertAlmostEqual(actual,value,places=3)
    def test_no_text(self):
        with pymupdf.open() as doc:self.assertEqual(page_text(doc.new_page())['blocks'],[])

if __name__=='__main__':unittest.main()
