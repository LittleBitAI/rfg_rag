import io
import json
from unittest.mock import Mock

import numpy as np
import pymupdf
import pytest
from PIL import Image

from rag.config import load_config
from rag.preprocessing import parsing
from rag.preprocessing.ocr_selection import SelectionParser


@pytest.fixture
def selector(tmp_path):
    delegate = Mock()
    delegate._analyze_image.return_value = 'unchanged Vision response'
    parser = SelectionParser(delegate, {'model_dir': str(tmp_path / 'missing'),
        'cache_dir': str(tmp_path / 'detector'), 'review_queue': str(tmp_path / 'review.jsonl')})
    source = tmp_path / 'source.hwp'
    source.write_bytes(b'source fixture')
    parser.set_source(source)
    parser.set_location(format='hwp', image_name='figure.png', marker_start=100)
    return parser


def decision(state):
    return {'classification': state, 'reason': 'fixed test evidence', 'text_detection': {}}


def test_off_preserves_original_parser_and_document(monkeypatch):
    delegate = object()
    expected = {'source': 'fixture', 'records': []}
    monkeypatch.setattr(parsing, '_ocr_parser', lambda cfg, callback: delegate)
    def parse(path, settings, parser, saved_rows):
        assert saved_rows is None
        assert parser is delegate
        return expected
    monkeypatch.setattr(parsing, '_parse_file', parse)
    assert parsing.parse_documents(['mock.hwp'], {}, True, {'usd_per_1m_tokens': [0.25, 0.025, 2.0]}) == [expected]


def test_candidate_keeps_vision_response(selector):
    selector.detector.classify = lambda *args: decision('OCR_CANDIDATE')
    assert selector._analyze_image(Image.new('RGB', (10, 10))) == 'unchanged Vision response'
    selector.delegate._analyze_image.assert_called_once()


@pytest.mark.parametrize('state', ['REVIEW_REQUIRED', 'OCR_UNNECESSARY'])
def test_non_candidate_never_calls_api_and_review_retained(selector, state):
    selector.detector.classify = lambda *args: decision(state)
    assert selector._analyze_image(Image.new('RGB', (10, 10))) == ''
    selector.delegate._analyze_image.assert_not_called()
    entries = [json.loads(s) for s in selector.audit_path.read_text().splitlines()]
    assert entries[0]['source']['document_sha256']
    assert entries[0]['location']['marker_start'] == 100
    assert selector.review_path.exists() == (state == 'REVIEW_REQUIRED')


def test_missing_model_is_review_without_api(selector):
    image = Image.new('RGB', (20, 20), 'white')
    image.putpixel((3, 3), (0, 0, 0))
    assert selector._analyze_image(image) == ''
    selector.delegate._analyze_image.assert_not_called()
    assert json.loads(selector.review_path.read_text())['classification'] == 'REVIEW_REQUIRED'


def test_pdf_candidate_response_object_preserved(selector):
    selector.detector.classify = lambda *args: decision('OCR_CANDIDATE')
    payload = io.BytesIO()
    np.save(payload, np.zeros((5, 5, 3), dtype=np.uint8))
    blob = Mock()
    blob.as_bytes.return_value = payload.getvalue()
    response = object()
    selector.delegate.lazy_parse.return_value = iter([response])
    assert list(selector.lazy_parse(blob)) == [response]


def test_bad_pdf_blob_is_persistent_review(selector):
    blob = Mock()
    blob.as_bytes.return_value = b'not a numpy image'
    assert list(selector.lazy_parse(blob))[0].page_content == ''
    assert selector.review_path.exists()
    selector.delegate.lazy_parse.assert_not_called()


def test_on_wraps_existing_vision_parser(monkeypatch, tmp_path):
    delegate = object()
    make_parser = Mock(return_value=delegate)
    monkeypatch.setattr(parsing, '_ocr_parser', make_parser)
    seen = []
    def parse(path, settings, parser, saved_rows):
        assert saved_rows is None
        assert isinstance(parser, SelectionParser)
        assert parser.delegate is delegate
        seen.append(path)
        return {'source': 'fixture', 'records': []}
    monkeypatch.setattr(parsing, '_parse_file', parse)
    settings = {'craft': {'enabled': True, 'model_dir': str(tmp_path / 'missing'),
        'cache_dir': str(tmp_path / 'detector'), 'review_queue': str(tmp_path / 'review.jsonl')}}
    ocr_cfg = {'model': 'selected-vision-model', 'max_tokens': 1234,
               'reasoning_effort': 'high', 'usd_per_1m_tokens': [0.25, 0.025, 2.0]}
    parsing.parse_documents(['mock.hwp'], settings, True, ocr_cfg)
    assert seen == ['mock.hwp']
    assert make_parser.call_args.args[0] is ocr_cfg
    assert make_parser.call_args.args[1].subject == 'mock.hwp'


def test_repeated_hwp_preserves_locations_and_vision_reuse(selector, tmp_path):
    selector.detector.classify = lambda *args: decision('OCR_CANDIDATE')
    Image.new('RGB', (10, 10)).save(tmp_path / 'figure.png')
    text = '[IMAGE: figure.png]\n[IMAGE: figure.png]\n[IMAGE: figure.png]'
    output, captions = parsing._ocr_hwp_images(text, str(tmp_path), selector, 3)
    assert len(captions) == 3
    assert output.count('[[IMG:') == 3
    selector.delegate._analyze_image.assert_called_once()
    entries = [json.loads(line) for line in selector.audit_path.read_text().splitlines()]
    assert len({entry['location']['marker_start'] for entry in entries}) == 3


def test_pdf_location_trace(selector):
    page = Mock()
    page.number = 2
    page.get_image_rects.return_value = [[1, 2, 30, 40]]
    parsing._image_selection_location(selector, page, 4, 9)
    assert selector.location == {'format': 'pdf', 'page': 3, 'image_index': 4,
        'xref': 9, 'bbox_points': [[1, 2, 30, 40]]}


def _write_pdf_image(tmp_path, mode):
    image = Image.new(mode, (20, 20), 'white')
    image.putpixel((3, 3), 0 if mode == 'L' else (0, 0, 0))
    payload = io.BytesIO()
    image.save(payload, format='PNG')
    path = tmp_path / f'{mode}.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), 'Preserved document body with project requirements.')
        page.insert_image(pymupdf.Rect(40, 60, 100, 120), stream=payload.getvalue())
        document.save(path)
    return path


@pytest.mark.parametrize('mode', ['RGB', 'L'])
def test_real_pdf_candidate_reaches_vision(selector, tmp_path, mode):
    from langchain_core.documents import Document

    path = _write_pdf_image(tmp_path, mode)
    selector.set_source(path)
    selector.detector.classify = lambda *args: decision('OCR_CANDIDATE')
    response = Document(page_content='unchanged Vision response')
    selector.delegate.lazy_parse.return_value = iter([response])
    _, images = parsing._pdf_tables_images(str(path), selector)
    assert images == {1: ['unchanged Vision response']}
    selector.delegate.lazy_parse.assert_called_once()
    assert not selector.review_path.exists()


def test_pdf_location_failure_keeps_document_and_review(selector, tmp_path, monkeypatch):
    path = _write_pdf_image(tmp_path, 'RGB')
    settings = load_config()
    settings['parsing'].update(skip_first_pages=0, hanja_mode='none')
    monkeypatch.setattr(parsing, '_ocr_parser', lambda *args: selector)
    monkeypatch.setattr(pymupdf.Page, 'get_image_rects', Mock(side_effect=RuntimeError('broken placement')))
    documents = parsing.parse_documents([str(path)], settings['parsing'], True, settings['ocr'])
    assert len(documents) == 1
    assert 'Preserved document body' in documents[0]['records'][0]['text']
    entry = json.loads(selector.review_path.read_text(encoding='utf-8'))
    assert entry['classification'] == 'REVIEW_REQUIRED'
    assert entry['source']['source'] == path.name
    assert entry['source']['document_sha256']
    assert entry['location']['format'] == 'pdf'
    assert entry['location']['page'] == 1
    assert entry['location']['image_index'] == 0
    assert entry['location']['xref'] > 0
    assert entry['location']['bbox_points'] == []
    selector.delegate.lazy_parse.assert_not_called()
