"""선택적 탐지 게이트. 불확실한 이미지는 출처와 함께 검토 목록에 보존한다."""
import hashlib
import io
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from rag.preprocessing.craft_detector import Detector


class SelectionParser:
    def __init__(self, delegate, settings):
        self.delegate = delegate
        self.detector = Detector(settings['model_dir'], settings['cache_dir'], settings.get('settings'))
        self.review_path = Path(settings['review_queue'])
        self.audit_path = Path(settings['cache_dir']).parent / 'ocr_selection.jsonl'
        self.source = {}
        self.location = {}
        self.selected_images = {}

    def set_source(self, path):
        self.source = {'source': Path(path).name, 'document_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        self.location = {}
        self.selected_images = {}

    def set_location(self, **location):
        self.location = location

    def _select(self, image):
        with tempfile.TemporaryDirectory(prefix='craft_selection_') as root:
            path = Path(root) / 'image.png'
            image.convert('RGB').save(path)
            raster_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            asset = {'raster_path': path.name, 'raster_sha256': raster_sha}
            result = self.detector.classify(asset, root)
        name = self.location.get("image_name")
        if name:
            self.selected_images[name] = (result, raster_sha)
        self._record(result, raster_sha)
        return result['classification'] == 'OCR_CANDIDATE'

    def _record(self, result, image_sha):
        entry = dict(result, image_sha256=image_sha, source=self.source, location=self.location)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
        if result['classification'] == 'REVIEW_REQUIRED':
            self.review_path.parent.mkdir(parents=True, exist_ok=True)
            with self.review_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def record_repeated_image(self, name):
        if name in self.selected_images:
            result, image_sha = self.selected_images[name]
            self._record(result, image_sha)

    def record_error(self, reason):
        result = {'classification': 'REVIEW_REQUIRED', 'reason': reason}
        name = self.location.get('image_name')
        if name:
            self.selected_images[name] = (result, None)
        self._record(result, None)

    def _analyze_image(self, image):
        return self.delegate._analyze_image(image) if self._select(image) else ''

    def lazy_parse(self, blob):
        try:
            array = np.load(io.BytesIO(blob.as_bytes()))
            image = Image.fromarray(array)
        except (ValueError, OSError, TypeError):
            self.record_error('PDF image blob decode failed')
            from langchain_core.documents import Document
            yield Document(page_content='')
            return
        if self._select(image):
            yield from self.delegate.lazy_parse(blob)
        else:
            from langchain_core.documents import Document
            yield Document(page_content='')
