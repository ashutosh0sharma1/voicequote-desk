import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

(Path(__file__).parent / "data").mkdir(exist_ok=True)
TEMP = tempfile.TemporaryDirectory(prefix="tests-", dir=Path(__file__).parent / "data")
os.environ["VOICEQUOTE_DB"] = str(Path(TEMP.name) / "test.sqlite3")
from fastapi.testclient import TestClient
from app import app
from engine import analyze

class QuotesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_clean_extraction(self):
        result = analyze("Please quote two copper pipes and three steel brackets.")
        self.assertEqual(result["total"], "39.25")
        self.assertEqual([x["quantity"] for x in result["lines"]], [2, 3])

    def test_ambiguous_quantity_withholds_total(self):
        result = analyze("two or three copper pipes and one sealant cartridge")
        self.assertIsNone(result["total"])
        self.assertIsNone(result["lines"][0]["quantity"])
        self.assertEqual(result["known_subtotal"], "9.99")

    def test_missing_price_and_unknown_product(self):
        result = analyze("one installation service and four mystery valves")
        self.assertEqual(result["review_count"], 2)
        self.assertIsNone(result["total"])
        self.assertIsNone(result["lines"][1]["product_id"])

    def test_decimal_money_is_exact(self):
        result = analyze("three sealant cartridges")
        self.assertEqual(result["total"], "29.97")

    def test_bad_quantities_do_not_price(self):
        for value in ["-2", "0", "1.5", "1001", "two hundred", "several"]:
            with self.subTest(value=value):
                result = analyze(value + " copper pipes")
                self.assertIsNone(result["total"])

    def test_approximation_does_not_price(self):
        self.assertIsNone(analyze("about two copper pipes")["total"])

    def test_unknown_modifier_not_silently_ignored(self):
        self.assertIsNone(analyze("two red copper pipes")["total"])

    def test_empty_rejected(self):
        self.assertEqual(self.client.post("/api/analyze", json={"transcript":" "}).status_code, 422)

    def test_review_preserves_original_and_idempotence(self):
        original = "two or three copper pipes"
        item = self.client.post("/api/analyze", json={"transcript": original}).json()
        payload = {"analysis_id": item["id"], "request_id": "repeat-test-123", "resolutions": [{"index":0,"product_id":"CP-01","quantity":3}]}
        first = self.client.post("/api/quotes", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        quote = first.json()["quote"]
        self.assertEqual(quote["original_transcript"], original)
        self.assertEqual(quote["validated_fields"]["total"], "37.50")
        self.assertTrue(quote["created_at"].endswith("+00:00"))
        second = self.client.post("/api/quotes", json=payload).json()
        self.assertTrue(second["replayed"])
        self.assertEqual(quote["id"], second["quote"]["id"])
        payload["resolutions"][0]["quantity"] = 4
        self.assertEqual(self.client.post("/api/quotes", json=payload).status_code, 409)

    def test_strict_review_quantity_and_catalog(self):
        item = self.client.post("/api/analyze", json={"transcript":"two copper pipes"}).json()
        for quantity in [0, -1, 1.5, True, "2", 1001]:
            payload = {"analysis_id":item["id"],"request_id":"invalid-123","resolutions":[{"index":0,"product_id":"CP-01","quantity":quantity}]}
            self.assertEqual(self.client.post("/api/quotes",json=payload).status_code,422)
        payload["resolutions"][0].update(product_id="MISSING", quantity=2)
        self.assertEqual(self.client.post("/api/quotes",json=payload).status_code,422)

    def test_client_cannot_supply_price(self):
        item = self.client.post("/api/analyze", json={"transcript":"two copper pipes"}).json()
        payload = {"analysis_id":item["id"],"request_id":"price-123","resolutions":[{"index":0,"product_id":"CP-01","quantity":2,"unit_price":"0.01"}]}
        self.assertEqual(self.client.post("/api/quotes",json=payload).status_code,422)

    def test_missing_price_saves_as_draft(self):
        item = self.client.post("/api/analyze", json={"transcript":"one installation service"}).json()
        result = self.client.post("/api/quotes", json={"analysis_id":item["id"],"request_id":"draft-1234"}).json()["quote"]
        self.assertEqual(result["validated_fields"]["status"],"review_required")
        self.assertIsNone(result["validated_fields"]["total"])
        csv = self.client.get('/api/quotes/'+result["id"]+'/csv')
        self.assertEqual(csv.status_code,200)
        self.assertIn("original_transcript",csv.text)
        self.assertIn("No fixture price",csv.text)

    def test_bad_audio_extension_rejected(self):
        with patch('app.cached_model', return_value=None) as model:
            self.assertEqual(self.client.post('/api/audio',files={"file":("bad.txt",b"hello","text/plain")}).status_code,422)
            model.assert_not_called()

    def test_empty_audio_rejected_before_model_lookup(self):
        with patch('app.cached_model', return_value=None) as model:
            self.assertEqual(self.client.post('/api/audio',files={"file":("empty.wav",b"","audio/wav")}).status_code,422)
            model.assert_not_called()

    def test_missing_model_returns_unavailable_without_starting_worker(self):
        with patch('app.cached_model', return_value=None), patch('app.subprocess.run') as worker:
            self.assertEqual(self.client.post('/api/audio',files={"file":("sample.wav",b"synthetic","audio/wav")}).status_code,503)
            worker.assert_not_called()

if __name__ == "__main__":
    unittest.main(verbosity=2)
