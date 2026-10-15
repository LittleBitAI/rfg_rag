"""가짜 탐지 결과로 안전 조건을 검증하며 문자 인식기 로드·가중치 다운로드는 금지한다."""

import json, sys, tempfile, unittest, hashlib
from pathlib import Path
from PIL import Image


from rag.preprocessing.craft_detector import Detector


class Reader:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def detect(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Detector failure")
        return [[[0, 10, 0, 10]]], [[]]


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.model = self.root / "models"
        self.model.mkdir()
        (self.model / "craft_mlt_25k.pth").write_bytes(b"offline fixture")
        p = self.root / "image.png"
        im = Image.new("RGB", (40, 40), "white")
        im.putpixel((10, 10), (0, 0, 0))
        im.save(p)
        self.asset = dict(
            raster_path="image.png",
            raster_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        self.cache = self.root / "detector_cache"

    def tearDown(self):
        self.tmp.cleanup()

    def test_detector_error_keeps_review(self):
        self.assertEqual(
            Detector(self.model, self.cache, reader=Reader(True)).classify(
                self.asset, self.root
            )["classification"],
            "REVIEW_REQUIRED",
        )

    def test_missing_model_keeps_review(self):
        self.assertEqual(
            Detector(self.root / "missing", self.cache).classify(self.asset, self.root)[
                "classification"
            ],
            "REVIEW_REQUIRED",
        )

    def test_decode_error_keeps_review(self):
        p = self.root / "broken.png"
        p.write_bytes(b"broken")
        a = dict(
            raster_path=p.name, raster_sha256=hashlib.sha256(p.read_bytes()).hexdigest()
        )
        self.assertEqual(
            Detector(self.model, self.cache).classify(a, self.root)["classification"],
            "REVIEW_REQUIRED",
        )

    def test_no_regions_not_excluded(self):
        r = Reader()
        r.detect = lambda *a, **k: ([[]], [[]])
        self.assertEqual(
            Detector(self.model, self.cache, reader=r).classify(self.asset, self.root)[
                "classification"
            ],
            "REVIEW_REQUIRED",
        )

    def test_uniform_only_unnecessary(self):
        p = self.root / "blank.png"
        Image.new("RGB", (20, 20), "white").save(p)
        a = dict(
            raster_path=p.name, raster_sha256=hashlib.sha256(p.read_bytes()).hexdigest()
        )
        self.assertEqual(
            Detector(self.root / "missing", self.cache).classify(a, self.root)[
                "classification"
            ],
            "OCR_UNNECESSARY",
        )

    def test_hash_mismatch_keeps_review(self):
        a = dict(self.asset, raster_sha256="wrong")
        self.assertEqual(
            Detector(self.model, self.cache).classify(a, self.root)["classification"],
            "REVIEW_REQUIRED",
        )

    def test_duplicate_asset_cache_and_config_change(self):
        recog = self.root / "ocr_cache"
        recog.mkdir()
        f = recog / "approved.json"
        f.write_text("approved")
        r = Reader()
        d = Detector(self.model, self.cache, reader=r)
        self.assertEqual(
            d.classify(self.asset, self.root)["classification"], "OCR_CANDIDATE"
        )
        self.assertTrue(
            d.classify(self.asset, self.root)["text_detection"]["cache_reused"]
        )
        self.assertEqual(r.calls, 1)
        changed = Detector(
            self.model, self.cache, settings={"text_threshold": 0.6}, reader=r
        )
        changed.classify(self.asset, self.root)
        self.assertEqual(r.calls, 2)
        self.assertEqual(f.read_text(), "approved")

    def test_model_SHA_change_invalidates_detector_only(self):
        r = Reader()
        d = Detector(self.model, self.cache, reader=r)
        d.classify(self.asset, self.root)
        (self.model / "craft_mlt_25k.pth").write_bytes(b"changed fixture")
        Detector(self.model, self.cache, reader=r).classify(self.asset, self.root)
        self.assertEqual(r.calls, 2)


if __name__ == "__main__":
    unittest.main()
