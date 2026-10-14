"""문자 인식 없이 CRAFT 영역만 탐지하며 이미지·설정별 캐시를 별도로 유지한다."""

from pathlib import Path
import hashlib, json, time
from PIL import Image

DEFAULT = dict(
    canvas_size=2560,
    mag_ratio=1.0,
    min_size=5,
    text_threshold=0.5,
    low_text=0.3,
    link_threshold=0.3,
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Detector:
    def __init__(self, modeldir, cache, settings=None, reader=None):
        self.modeldir = Path(modeldir)
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.params = dict(DEFAULT, **(settings or {}))
        self.reader = reader
        self.init_error = None
        model = self.modeldir / "craft_mlt_25k.pth"
        self.model_sha = digest(model) if model.is_file() else None
        import importlib.metadata

        try:
            version = importlib.metadata.version("easyocr")
        except importlib.metadata.PackageNotFoundError:
            version = "unavailable"
        self.config = dict(
            engine="CRAFT",
            params=self.params,
            model_sha256=self.model_sha,
            easyocr_version=version,
            recognizer=False,
        )
        self.config_sha = signature(self.config)

    def _reader(self):
        if self.reader is not None:
            return self.reader
        if not self.model_sha:
            raise RuntimeError("Local CRAFT model absent")
        import torch, easyocr

        torch.set_num_threads(4)
        self.reader = easyocr.Reader(
            ["ko", "en"],
            gpu=False,
            model_storage_directory=str(self.modeldir),
            download_enabled=False,
            recognizer=False,
            verbose=False,
        )
        return self.reader

    def classify(self, asset, root):
        start = time.perf_counter()
        ev = dict(
            detector_config=self.config,
            detector_config_sha256=self.config_sha,
            recognition_executed=False,
            cache_reused=False,
        )

        def out(state, why):
            return dict(
                classification=state,
                reason=why,
                text_detection=dict(ev, elapsed_seconds=time.perf_counter() - start),
            )

        rel = asset.get("raster_path")
        if not rel:
            return out("REVIEW_REQUIRED", "Unsupported raster; keep review item")
        try:
            base = Path(root).resolve()
            p = (base / rel).resolve()
            p.relative_to(base)
            actual = digest(p)
            if actual != asset.get("raster_sha256"):
                return out(
                    "REVIEW_REQUIRED",
                    "Raster SHA mismatch; stale source/cache cannot certify",
                )
            ev["raster_sha256"] = actual
            with Image.open(p) as im:
                rgb = im.convert("RGB")
                ev.update(
                    width=rgb.width,
                    height=rgb.height,
                    uniform_pixel_evidence=all(a == b for a, b in rgb.getextrema()),
                )
            if ev["uniform_pixel_evidence"]:
                return out(
                    "OCR_UNNECESSARY",
                    "All visible raster pixels uniform; image-only scope",
                )
            cache = self.cache / (actual + "_" + self.config_sha + ".json")
            previous = self._cached(cache, actual)
            if previous:
                return previous
            reader = self._reader()
            horizontal, free = reader.detect(str(p), **self.params)
            boxes = horizontal[0]
            polys = free[0]
            ev.update(
                horizontal_boxes=[list(map(int, b)) for b in boxes],
                free_polygons=[
                    [[float(c) for c in pt] for pt in poly] for poly in polys
                ],
                regions=len(boxes) + len(polys),
            )
            result = out(
                "OCR_CANDIDATE" if boxes or polys else "REVIEW_REQUIRED",
                "Text-like regions detected"
                if boxes or polys
                else "No region detected; tiny text or symbols may be missed",
            )
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(result, ensure_ascii=False))
            tmp.replace(cache)
            return result
        except Exception as err:
            ev["error_type"] = type(err).__name__
            return out("REVIEW_REQUIRED", "Decode/detector/model error; never discard")

    def _cached(self, path, raster_sha):
        if not path.exists():
            return None
        try:
            old = json.loads(path.read_text())
            evidence = old["text_detection"]
            valid = (
                evidence["raster_sha256"] == raster_sha
                and evidence["detector_config_sha256"] == self.config_sha
            )
            if (
                valid
                and old["classification"] in ["OCR_CANDIDATE", "REVIEW_REQUIRED"]
                and "regions" in evidence
            ):
                evidence["cache_reused"] = True
                return old
        except (ValueError, KeyError, TypeError):
            pass
        return None
