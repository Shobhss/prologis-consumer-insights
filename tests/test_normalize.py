"""Run with: .venv/bin/python -m pytest tests  (or python -m unittest discover tests)"""
import unittest

from pipeline.extract import verify_quote, confidence
from pipeline.normalize import split_transcript, chunk_text, split_filing_sections


class TestGrounding(unittest.TestCase):
    def test_exact_quote_passes(self):
        chunk = "We opened three new fulfillment centers in Texas during 2026."
        self.assertTrue(verify_quote("opened three new fulfillment centers in Texas", chunk))

    def test_whitespace_and_curly_quotes_normalized(self):
        chunk = "Amazon’s   network\nexpanded in New Jersey."
        self.assertTrue(verify_quote("Amazon's network expanded in New Jersey", chunk))

    def test_paraphrase_fails(self):
        chunk = "We opened three new fulfillment centers in Texas."
        self.assertFalse(verify_quote("Amazon opened 3 FCs in TX", chunk))

    def test_confidence_bounds(self):
        self.assertAlmostEqual(confidence(3, 3, 3), 1.0)
        self.assertLess(confidence(1, 1, 1), 0.4)


class TestTranscript(unittest.TestCase):
    def test_colon_layout(self):
        text = ("TAKEAWAYS\n- Revenue -- $200B\nFull Conference Call Transcript\n"
                "Operator: Welcome.\nAndy Jassy: Thanks. We added capacity in Ohio.\n")
        turns = split_transcript(text)
        self.assertEqual([t[0] for t in turns], ["Operator", "Andy Jassy"])
        self.assertIn("Ohio", turns[1][1])

    def test_dash_layout(self):
        text = "Dave Fildes -- Director, Investor Relations\nHello.\nBrian Olsavsky -- CFO\nCapex was $10B.\n"
        turns = split_transcript(text)
        self.assertEqual(len(turns), 2)
        self.assertTrue(turns[1][0].startswith("Brian Olsavsky"))


class TestChunking(unittest.TestCase):
    def test_chunks_respect_size(self):
        text = "\n\n".join(["para " * 200] * 10)
        for c in chunk_text(text, size=2000, overlap=100):
            self.assertLessEqual(len(c), 2000)

    def test_10q_part_aware(self):
        text = ("PART I. FINANCIAL INFORMATION\nItem 1. Financial Statements\n" + "x " * 400 +
                "\nItem 2. MD&A\n" + "y " * 400 + "\nPART II. OTHER INFORMATION\nItem 1. Legal\n" + "z " * 400 +
                "\nItem 1A. Risk Factors\n" + "w " * 400 + "\nItem 6. Exhibits\n" + "v " * 200)
        secs = split_filing_sections(text, form="10-Q")
        self.assertIn("Part I Item 2 MD&A", secs)
        self.assertIn("Part II Item 1A Risk Factors", secs)


if __name__ == "__main__":
    unittest.main()
