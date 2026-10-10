"""Real in-memory documents and bounded worker contracts; no external services."""
import asyncio
import csv
import hashlib
import io
import json
import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from truth_backend import extraction, providers
from truth_backend.security import Fetched, ServiceError


def make_pdf(texts, *, encrypted=False, oversized_stream=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            body = ("BT /F1 12 Tf 72 720 Td (" + escaped + ") Tj ET").encode("ascii")
            if oversized_stream:
                body += b" " * (extraction.MAX_PDF_STREAM_BYTES + 1)
            stream = DecodedStreamObject()
            stream.set_data(body)
            page[NameObject("/Contents")] = writer._add_object(stream.flate_encode() if oversized_stream else stream)
    if encrypted:
        writer.encrypt("synthetic-pdf-password")
    target = io.BytesIO()
    writer.write(target)
    return target.getvalue()


def row():
    return {"url": "https://example.com/record", "title": "Original source", "snippet": "Search excerpt only.", "raw_content": "", "published_at": None}


def test_real_pdf_text_is_extracted_in_a_separate_bounded_worker():
    content = make_pdf(["Original record: the 2024 count is 17.", "The 2025 count is 19 under the same definition."])
    result = asyncio.run(extraction.extract_document(content, "application/pdf", language="en"))
    assert result.format == "pdf"
    assert "2024 count is 17" in result.text and "2025 count is 19" in result.text
    assert "2 of 2 PDF pages" in " ".join(result.notices)
    assert "No OCR" in " ".join(result.notices)


def test_real_pdf_page_limit_is_disclosed_and_unread_pages_never_enter_evidence():
    content = make_pdf([f"Original record on page {index:02d}." for index in range(1, 15)])
    result = asyncio.run(extraction.extract_document(content, "application/pdf", language="en"))
    assert "page 12" in result.text and "page 13" not in result.text
    assert "12 of 14 PDF pages" in " ".join(result.notices)
    assert "truncated" in " ".join(result.notices)


def test_real_pdf_character_limit_is_disclosed():
    result = asyncio.run(extraction.extract_document(make_pdf(["Original text. " * 2000]), "application/pdf", language="en"))
    assert 15_900 <= len(result.text) <= extraction.MAX_TEXT_CHARACTERS
    assert "truncated" in " ".join(result.notices)


@pytest.mark.parametrize("content,expected", [
    (make_pdf([""]), "pdf_no_text"),
    (make_pdf(["An encrypted source record."], encrypted=True), "pdf_encrypted"),
    (b"%PDF-1.7\ninvalid synthetic-private-source-data", "pdf_invalid"),
    (make_pdf(["A compressed oversized stream."], oversized_stream=True), "pdf_resource_limit"),
])
def test_pdf_without_readable_text_or_exceeding_limits_fails_safely(content, expected):
    with pytest.raises(ServiceError) as caught:
        asyncio.run(extraction.extract_document(content, "application/pdf", language="en"))
    assert caught.value.code == expected
    assert "synthetic-private-source-data" not in caught.value.message
    assert "synthetic-pdf-password" not in caught.value.message


def test_pdf_magic_header_is_supported_when_server_uses_generic_binary_mime():
    result = asyncio.run(extraction.extract_document(make_pdf(["Original PDF text." ]), "application/octet-stream", language="en"))
    assert result.format == "pdf" and "Original PDF text." in result.text


@pytest.mark.parametrize("mime", ["application/pdf", "text/html", "text/csv"])
def test_document_byte_limit_is_enforced_before_parsing_or_worker_start(monkeypatch, mime):
    factory = AsyncMock()
    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", factory)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(extraction.extract_document(b"x" * (extraction.MAX_DOCUMENT_BYTES + 1), mime, language="en"))
    assert caught.value.code == "document_too_large"
    factory.assert_not_awaited()


class FakeWorker:
    def __init__(self, result=None, *, pending=False):
        self.returncode = None if pending else 0
        self.communicate_started = asyncio.Event()
        self.killed = False
        self.waited = False
        self.result = result or {"text": "Original worker text.", "pages": 1, "total_pages": 1, "truncated": False}
        self.pending = pending

    async def communicate(self, content):
        self.communicate_started.set()
        if self.pending:
            await asyncio.Future()
        return json.dumps(self.result).encode(), None

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        await asyncio.sleep(0)
        self.waited = True
        return self.returncode


def test_worker_never_inherits_api_credentials_or_source_headers(monkeypatch):
    monkeypatch.setenv("TRUTH_AI_API_KEY", "synthetic-ai-private-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-search-private-key")
    worker = FakeWorker()
    factory = AsyncMock(return_value=worker)
    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", factory)
    asyncio.run(extraction.extract_pdf(b"%PDF-synthetic", language="en"))
    args, kwargs = factory.call_args
    assert args[0] == sys.executable and args[1] == "-I" and args[-1] == "--pdf-worker"
    assert set(kwargs["env"]) <= {"SYSTEMROOT", "WINDIR", "PATH"}
    assert "synthetic-ai-private-key" not in str(factory.call_args)
    assert "synthetic-search-private-key" not in str(factory.call_args)
    assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
    assert kwargs["creationflags"] == (0x08000000 if os.name == "nt" else 0)


def test_pdf_timeout_kills_worker_and_awaits_exit_before_reporting(monkeypatch):
    worker = FakeWorker(pending=True)
    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", AsyncMock(return_value=worker))
    monkeypatch.setattr(extraction, "PDF_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(extraction.extract_pdf(b"%PDF-synthetic", language="en"))
    assert caught.value.code == "pdf_timeout" and worker.killed and worker.waited


def test_cancelled_pdf_request_kills_worker_and_awaits_exit(monkeypatch):
    async def scenario():
        worker = FakeWorker(pending=True)
        monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", AsyncMock(return_value=worker))
        task = asyncio.create_task(extraction.extract_pdf(b"%PDF-synthetic", language="en"))
        await worker.communicate_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker.killed and worker.waited
    asyncio.run(scenario())


def test_real_sleeping_child_is_terminated_on_hard_timeout(monkeypatch):
    original_factory = asyncio.create_subprocess_exec
    children = []
    async def sleeping_child(*args, **kwargs):
        process = await original_factory(sys.executable, "-I", "-c", "import time; time.sleep(60)", **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", sleeping_child)
    monkeypatch.setattr(extraction, "PDF_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(extraction.extract_pdf(b"%PDF-synthetic", language="en"))
    assert caught.value.code == "pdf_timeout"
    assert len(children) == 1 and children[0].returncode is not None and children[0].returncode != 0


def test_worker_refuses_to_import_pdf_parser_without_os_resource_limits(monkeypatch):
    import pypdf
    parser = Mock()
    monkeypatch.setattr(pypdf, "PdfReader", parser)
    monkeypatch.setattr(extraction, "_limit_pdf_worker", Mock(side_effect=OSError("synthetic-private-error")))
    assert extraction._pdf_worker_result(b"document") == {"error": "pdf_resource_limit"}
    parser.assert_not_called()


def test_parser_exceptions_never_cross_worker_boundary(monkeypatch):
    import pypdf
    monkeypatch.setattr(extraction, "_limit_pdf_worker", Mock())
    monkeypatch.setattr(pypdf, "PdfReader", Mock(side_effect=RuntimeError("synthetic-private-error-source-bytes")))
    assert extraction._pdf_worker_result(b"document") == {"error": "pdf_invalid"}


@pytest.mark.parametrize("result", [
    {"error": "synthetic-private-upstream-error"},
    {"text": "text", "pages": True, "total_pages": 1, "truncated": False},
    {"text": "text", "pages": 13, "total_pages": 13, "truncated": True},
    {"text": "text", "pages": 2, "total_pages": 1, "truncated": False},
    {"text": "x" * 16001, "pages": 1, "total_pages": 1, "truncated": True},
])
def test_invalid_worker_response_is_rejected_without_echoing_source_bytes(monkeypatch, result):
    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", AsyncMock(return_value=FakeWorker(result)))
    with pytest.raises(ServiceError) as caught:
        asyncio.run(extraction.extract_pdf(b"%PDF-synthetic", language="en"))
    assert caught.value.code == "pdf_invalid" and "synthetic-private" not in caught.value.message


def test_html_table_preserves_columns_empty_cells_and_merged_headers():
    content = b'<p>Original context.</p><table><tr><th rowspan="2">Year</th><th colspan="2">Counts</th></tr><tr><th>A</th><th>B</th></tr><tr><td>2024</td><td>10</td><td></td></tr></table>'
    result = extraction.extract_text_document(content, "text/html", language="en")
    assert result.format == "html" and result.has_tables
    assert "Year\tCounts\t\n\tA\tB\n2024\t10\t" in result.text
    assert "Merged cells" in " ".join(result.notices)
    assert "Original context." in result.text


def test_html_still_extracts_text_entities_inline_words_and_skips_executable_content():
    result = extraction.extract_text_document(b'<h1>Original &amp; record</h1><p>A <b>real</b> source.</p><script>synthetic-secret()</script><style>private</style>', "text/html")
    assert "Original & record" in result.text and "A real source." in result.text
    assert "synthetic-secret" not in result.text and "private" not in result.text
    assert providers.extract_text(b"Original text.", "text/plain") == "Original text."


@pytest.mark.parametrize("mime,body", [
    ("text/csv", 'Year,Label,Count,Empty\r\n2024,"A,B",0,\r\n'),
    ("text/tab-separated-values", 'Year\tLabel\tCount\tEmpty\r\n2024\tA,B\t0\t\r\n'),
])
def test_csv_and_tsv_preserve_field_values_zero_and_trailing_empty_column(mime, body):
    result = extraction.extract_text_document(body.encode(), mime, language="en")
    rows = list(csv.reader(io.StringIO(result.text), delimiter="\t"))
    assert rows == [["Year", "Label", "Count", "Empty"], ["2024", "A,B", "0", ""]]
    assert result.text.endswith("\t")
    assert "blanks are not replaced with zero" in " ".join(result.notices)


def test_quoted_multiline_csv_record_is_never_cut_between_its_lines():
    result = extraction.extract_text_document(b'Name,Count\n"line one\nline two",17\nNext,19\n', "text/csv", language="en")
    first_record_end = result.record_ends[0]
    excerpt, partial = extraction.table_excerpt(result, first_record_end + 10)
    assert excerpt == "Name\tCount" and partial is False
    excerpt, partial = extraction.table_excerpt(result, result.record_ends[1])
    assert list(csv.reader(io.StringIO(excerpt), delimiter="\t"))[1] == ["line one\nline two", "17"]


@pytest.mark.parametrize("body,expected", [
    ("Column\n" + "Value\n" * 501, "500-row"),
    (",".join("C" + str(index) for index in range(101)), "100-column"),
])
def test_tabular_row_and_column_resource_limits_are_disclosed(body, expected):
    result = extraction.extract_text_document(body.encode(), "text/csv", language="en")
    assert expected in " ".join(result.notices)
    rows = list(csv.reader(io.StringIO(result.text), delimiter="\t"))
    assert len(rows) <= 500 and all(len(row) <= 100 for row in rows)


def test_invalid_csv_fails_without_echoing_private_field_values():
    with pytest.raises(ServiceError) as caught:
        extraction.extract_text_document(b'Header\n"unclosed synthetic-private-field', "text/csv", language="en")
    assert caught.value.code == "invalid_table" and "synthetic-private-field" not in caught.value.message


def test_short_csv_is_retrieved_with_format_hash_and_trailing_empty_column(monkeypatch):
    content = b"Year,Count,Empty\n2024,17,\n"
    request = AsyncMock(return_value=Fetched("https://example.com/final.csv", content, "text/csv", 200))
    monkeypatch.setattr(providers, "pinned_request", request)
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, language="en"))
    assert evidence.status == "retrieved" and evidence.content_kind == "full_text" and evidence.document_format == "csv"
    assert evidence.url == "https://example.com/final.csv" and evidence.excerpt.endswith("\t")
    assert evidence.content_sha256 == hashlib.sha256(content).hexdigest()
    assert "Source body text" in evidence.context and "complete rows" in evidence.context and limitation
    assert request.call_args.kwargs["max_bytes"] == 1_500_000 and request.call_args.kwargs["timeout"] == 12


def test_pdf_source_integration_preserves_actual_text_format_and_response_bytes_hash(monkeypatch):
    content = make_pdf(["Original PDF record: 2024 has 17 entries."])
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/record.pdf", content, "application/pdf", 200)))
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, language="en"))
    assert evidence.status == "retrieved" and evidence.document_format == "pdf"
    assert "2024 has 17 entries" in evidence.excerpt
    assert evidence.content_sha256 == hashlib.sha256(content).hexdigest()
    assert "No OCR" in evidence.context and "No OCR" in limitation


@pytest.mark.parametrize("language,expected", [("zh-CN", "不进行 OCR"), ("en", "OCR is not performed"), ("ja", "OCR は行いません")])
def test_unreadable_pdf_falls_back_to_explicit_search_excerpt_in_requested_language(monkeypatch, language, expected):
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/record.pdf", make_pdf([""]), "application/pdf", 200)))
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, language=language))
    assert evidence.status == "snippet_only" and evidence.document_format == "unknown" and evidence.content_sha256 is None
    assert evidence.excerpt == "Search excerpt only." and expected in limitation


def test_tabular_excerpt_preserves_header_and_whole_rows_even_with_matching_later_query(monkeypatch):
    content = ("Year,Count\n" + "2020,17\n" * 30 + "2099,99\n").encode()
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/table.csv", content, "text/csv", 200)))
    evidence, _ = asyncio.run(providers.fetch_evidence(row(), 1, "2099 count", max_excerpt=50, language="en"))
    rows = list(csv.reader(io.StringIO(evidence.excerpt), delimiter="\t"))
    assert rows[0] == ["Year", "Count"] and all(len(record) == 2 for record in rows)
    assert len(evidence.excerpt) <= 50 and "2099" not in evidence.excerpt
    assert "not selected by query keywords" in evidence.context


def test_unsafe_pdf_redirect_is_rejected_before_any_parser_or_subprocess(monkeypatch):
    secret = "synthetic-source-secret"
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched(
        "https://example.com/record.pdf?session=" + secret, b"%PDF-synthetic", "application/pdf", 200)))
    parser = AsyncMock()
    monkeypatch.setattr(providers, "extract_document", parser)
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, headers={"Cookie": "session=" + secret}, language="en"))
    assert evidence is None and secret not in limitation
    parser.assert_not_awaited()


def test_declared_csv_text_is_not_misclassified_as_pdf_from_a_field_prefix():
    result = asyncio.run(extraction.extract_document(b"%PDF-not-a-file,Count\nA,17\n", "text/csv", language="en"))
    assert result.format == "csv" and "%PDF-not-a-file\tCount" in result.text


def test_unknown_character_encoding_falls_back_safely_and_loss_is_disclosed():
    result = extraction.extract_text_document(b"Original text with a byte: \xff", "text/plain; charset=unsupported-codec", language="en")
    assert "\ufffd" in result.text and "replacement characters" in " ".join(result.notices)
    result = extraction.extract_text_document("Original caf\u00e9".encode("latin-1"), "text/plain; charset=latin-1", language="en")
    assert result.text == "Original caf\u00e9" and not result.notices


def test_html_table_column_overflow_is_disclosed_instead_of_silently_losing_cells():
    cells = "<td>A</td>" * 99 + '<td colspan="2">Last</td>'
    result = extraction.extract_text_document(("<table><tr>" + cells + "</tr></table>").encode(), "text/html", language="en")
    assert len(next(csv.reader(io.StringIO(result.text), delimiter="\t"))) == 100
    assert "exceeded" in " ".join(result.notices)


def test_oversized_first_table_row_is_cut_with_an_explicit_column_warning(monkeypatch):
    content = ("LongField,Count\n" + "X" * 100 + ",17\n").encode()
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/table.csv", content, "text/csv", 200)))
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, max_excerpt=5, language="en"))
    assert evidence.excerpt == "LongF" and "column correspondence may be incomplete" in limitation


@pytest.mark.parametrize("language,expected", [("zh-CN", "不支持音视频"), ("en", "audiovisual content are unsupported"), ("ja", "音声・動画には未対応")])
def test_unsupported_binary_body_remains_unknown_with_localized_limitation(monkeypatch, language, expected):
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/audio", b"binary", "audio/mpeg", 200)))
    evidence, limitation = asyncio.run(providers.fetch_evidence(row(), 1, language=language))
    assert evidence.document_format == "unknown" and evidence.content_sha256 is None
    assert evidence.content_kind == "snippet" and expected in limitation
