"""Bounded source extraction; PDF parsing runs in a disposable, memory-limited process.

The worker receives only document bytes over stdin. It never imports the application,
inherits API credentials, loads dotenv, writes the document to disk, or executes PDF JS.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


MAX_DOCUMENT_BYTES = 1_500_000
MAX_TEXT_CHARACTERS = 16_000
MAX_PDF_PAGES = 12
MAX_PDF_STREAM_BYTES = 8_000_000
PDF_TIMEOUT_SECONDS = 6
PDF_MEMORY_BYTES = 512 * 1024 * 1024
MAX_TABLE_ROWS = 500
MAX_TABLE_COLUMNS = 100


@dataclass
class Extraction:
    text: str
    format: str
    notices: list[str] = field(default_factory=list)
    has_tables: bool = False
    record_ends: list[int] = field(default_factory=list)


def _tr(zh: str, en: str, ja: str, language: str) -> str:
    # Keep the standalone worker independent of imports in the app package.
    from .i18n import tr
    return tr(zh, en, ja, language)


def _error(code: str, language: str):
    from .security import ServiceError
    messages = {
        "unsupported_content": ("此版本支持 HTML、纯文本、文本型 PDF、CSV 与 TSV；不支持音视频或其他二进制格式。", "Supported formats are HTML, plain text, text-based PDF, CSV, and TSV; other binary formats and audiovisual content are unsupported.", "HTML、プレーンテキスト、テキスト PDF、CSV、TSV に対応しています。その他のバイナリ形式や音声・動画には未対応です。"),
        "document_too_large": ("来源文件超过 1.5 MB 安全读取上限。", "The source file exceeds the 1.5 MB safety limit.", "情報源ファイルが安全上限の 1.5 MB を超えています。"),
        "invalid_table": ("CSV/TSV 格式无效或单个字段超过解析上限；未猜测修复。", "CSV/TSV data is invalid or a field exceeds the parsing limit; no guessed repair was applied.", "CSV/TSV の形式が不正、またはフィールドが解析上限を超えています。推測による修復はしていません。"),
        "pdf_timeout": ("PDF 解析超过 6 秒硬时限，解析进程已终止；本版不进行 OCR。", "PDF parsing exceeded its six-second hard deadline; the worker was terminated. OCR is not performed.", "PDF 解析が 6 秒の上限を超えたため、プロセスを終了しました。OCR は行いません。"),
        "pdf_unavailable": ("当前环境无法启动受资源限制的 PDF 解析进程，未在服务进程内解析。", "A resource-limited PDF worker could not be started in this environment. Parsing was not attempted inside the server process.", "この環境では資源制限付き PDF プロセスを起動できません。サーバープロセス内での解析は行いません。"),
        "pdf_dependency_missing": ("未安装 pypdf，无法提取 PDF 文本；请安装项目依赖。", "pypdf is unavailable; install the project dependencies to extract PDF text.", "pypdf が利用できません。PDF テキストを抽出するにはプロジェクトの依存関係をインストールしてください。"),
        "pdf_resource_limit": ("PDF 超过解析资源限制，或当前系统无法施加内存限制；未继续解析。", "The PDF exceeded parser resource limits, or this system could not enforce the memory limit; parsing stopped.", "PDF が解析の資源上限を超えたか、システムがメモリ制限を適用できないため、解析を中止しました。"),
        "pdf_encrypted": ("PDF 已加密；本版不接收或尝试 PDF 解锁密码。", "The PDF is encrypted. This version does not accept or attempt PDF unlock passwords.", "PDF が暗号化されています。このバージョンは PDF の解除パスワードを受け付けず、解除も試みません。"),
        "pdf_no_text": ("PDF 未检出可提取文字，可能为空页、扫描件或字体不受支持；本版不进行 OCR。", "No extractable PDF text was found. Pages may be empty, scanned, or use unsupported fonts; OCR is not performed.", "抽出可能な PDF テキストが見つかりません。空白、スキャン画像、未対応フォントの可能性があります。OCR は行いません。"),
        "pdf_invalid": ("PDF 损坏、结构不受支持或解析失败；未把错误内容当作证据。", "The PDF is damaged, unsupported, or could not be parsed; error content was not treated as evidence.", "PDF が破損、未対応の構造、または解析不能です。エラー内容を証拠として扱っていません。"),
    }
    chosen = code if code in messages else "pdf_invalid"
    return ServiceError(chosen, _tr(*messages[chosen], language))


def _decode(content: bytes, content_type: str) -> str:
    match = re.search(r"charset=[\"']?([\w-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8-sig"
    try:
        return content.decode(encoding, errors="replace")
    except LookupError:
        return content.decode("utf-8-sig", errors="replace")


def _tabular_rows(rows: list[list[str]]) -> str:
    target = io.StringIO(newline="")
    writer = csv.writer(target, delimiter="\t", lineterminator="\n")
    writer.writerows(rows)
    return target.getvalue()[:-1] if target.tell() else ""


def table_excerpt(document: Extraction, max_length: int) -> tuple[str, bool]:
    """Keep the beginning/header and complete records; report an oversized first row."""
    if len(document.text) <= max_length:
        return document.text, False
    ends = document.record_ends
    end = max((position for position in ends if position <= max_length), default=0) if ends else document.text.rfind("\n", 0, max_length + 1)
    if end > 0:
        return document.text[:end], False
    return document.text[:max_length], True


class SourceHTMLParser(HTMLParser):
    """Keep table cells in columns, without inventing repeated merged-cell values."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.table_depth = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.cell_span = (1, 1)
        self.occupied_until = {}
        self.has_tables = False
        self.merged = False
        self.nested = False
        self.truncated = False

    def _finish_cell(self):
        if self.cell is None:
            return
        if self.row is None:
            self.row = []
        column = len(self.row)
        row_index = len(self.rows)
        while self.occupied_until.get(column, 0) > row_index and column < MAX_TABLE_COLUMNS:
            self.row.append("")
            column += 1
        colspan, rowspan = self.cell_span
        if column + colspan > MAX_TABLE_COLUMNS:
            self.truncated = True
        if column < MAX_TABLE_COLUMNS:
            value = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append(value)
            for covered in range(column, min(column + colspan, MAX_TABLE_COLUMNS)):
                if covered > column:
                    self.row.append("")
                if rowspan > 1:
                    self.occupied_until[covered] = row_index + rowspan
        else:
            self.truncated = True
        self.cell = None

    def _finish_row(self):
        self._finish_cell()
        if self.row is not None:
            if len(self.rows) < MAX_TABLE_ROWS:
                self.rows.append(self.row)
            else:
                self.truncated = True
            self.row = None

    def _finish_table(self):
        self._finish_row()
        width = max((len(row) for row in self.rows), default=0)
        rows = [row + [""] * (width - len(row)) for row in self.rows]
        self.parts.append(_tabular_rows(rows))
        self.parts.append("\n")
        self.rows, self.occupied_until = [], {}

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if self.skip:
            return
        if tag == "table":
            self.table_depth += 1
            self.has_tables = True
            if self.table_depth > 1:
                self.nested = True
            else:
                self.parts.append("\n")
        elif self.table_depth == 1 and tag == "tr":
            self._finish_row()
            self.row = []
        elif self.table_depth == 1 and tag in {"td", "th"}:
            self._finish_cell()
            self.cell = []
            attributes = dict(attrs)
            spans = []
            for name in ("colspan", "rowspan"):
                try:
                    span = int(attributes.get(name, "1"))
                except (ValueError, TypeError):
                    span = 1
                if not 1 <= span <= MAX_TABLE_COLUMNS:
                    self.truncated = True
                spans.append(min(max(span, 1), MAX_TABLE_COLUMNS))
            self.cell_span = tuple(spans)
            self.merged |= self.cell_span != (1, 1)
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            (self.cell if self.cell is not None else self.parts).append(" " if self.cell is not None else "\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "table" and self.table_depth:
            if self.table_depth == 1:
                self._finish_table()
            self.table_depth -= 1
        elif self.table_depth == 1 and tag in {"td", "th"}:
            self._finish_cell()
        elif self.table_depth == 1 and tag == "tr":
            self._finish_row()

    def handle_data(self, data):
        if not self.skip:
            if self.cell is not None:
                self.cell.append(data)
            else:
                self.parts.append(re.sub(r"[ \t\r\f\v]+", " ", data))

    def text(self):
        if self.table_depth:
            self._finish_table()
        return "".join(self.parts).strip(" \r\n")


def extract_text_document(content: bytes, content_type: str, *, language: str = "zh-CN") -> Extraction:
    if len(content) > MAX_DOCUMENT_BYTES:
        raise _error("document_too_large", language)
    mime = content_type.split(";", 1)[0].strip().lower()
    decoded = _decode(content, content_type)
    notices = []
    if "\ufffd" in decoded:
        notices.append(_tr("解码结果含替换字符，字符编码可能缺失或不匹配；请核对原文件。", "Decoded text contains replacement characters; the character encoding may be missing or mismatched. Inspect the original file.", "デコード結果に置換文字が含まれています。文字コードが不明または不一致の可能性があるため、元ファイルを確認してください。", language))
    if mime in {"text/csv", "application/csv", "text/tab-separated-values", "text/tsv"}:
        format_name = "tsv" if mime in {"text/tab-separated-values", "text/tsv"} else "csv"
        reader = csv.reader(io.StringIO(decoded, newline=""), delimiter="\t" if format_name == "tsv" else ",", strict=True)
        rows, truncated = [], False
        try:
            for index, row in enumerate(reader):
                if index >= MAX_TABLE_ROWS:
                    truncated = True
                    break
                if len(row) > MAX_TABLE_COLUMNS:
                    truncated = True
                rows.append(row[:MAX_TABLE_COLUMNS])
        except (csv.Error, UnicodeError):
            raise _error("invalid_table", language) from None
        serialized = [_tabular_rows([row]) for row in rows]
        text = "\n".join(serialized)
        ends, position = [], 0
        for record in serialized:
            position += len(record)
            ends.append(position)
            position += 1
        notices.append(_tr("表格按原始记录与字段顺序转为制表符分列文本；引号按 TSV 规则转义，未改写字段值或把空白补为零。", "Tabular records retain source row/field order as tab-separated text; quotes use TSV escaping. Field values are not rewritten and blanks are not replaced with zero.", "元のレコードとフィールドの順序をタブ区切りで保持します。引用符は TSV の規則でエスケープし、値の書き換えや空欄のゼロ補完は行いません。", language))
        if truncated:
            notices.append(_tr("表格超过最多 500 行或 100 列的解析上限，已截断。", "The table exceeded the 500-row or 100-column parsing limit and was truncated.", "表が 500 行または 100 列の解析上限を超えたため、切り詰めました。", language))
        result = Extraction(text, format_name, notices, True, ends)
    elif mime in {"text/html", "application/xhtml+xml"}:
        parser = SourceHTMLParser()
        parser.feed(decoded)
        parser.close()
        text = parser.text()
        if parser.has_tables:
            notices.append(_tr("HTML 表格按行与列保留为制表符分列文本；空白单元格保持空白，未推断单位或补值。", "HTML tables retain rows and columns as tab-separated text. Empty cells remain empty; units and missing values are not inferred.", "HTML の表は行と列をタブ区切りで保持します。空白セルは空白のままにし、単位や欠損値を推測しません。", language))
        if parser.merged:
            notices.append(_tr("合并单元格仅在起始位置保留文字，覆盖位置为空，不应把这些空位当作缺失值或零。", "Merged cells retain text only at their starting position; covered positions are empty and must not be interpreted as missing values or zero.", "結合セルの文字は開始位置にのみ保持し、覆われた位置は空欄です。欠損値やゼロと解釈しないでください。", language))
        if parser.nested:
            notices.append(_tr("嵌套表格已线性提取，无法保证其内层行列对应；需查看原文。", "Nested tables were extracted linearly; inner row/column correspondence is not guaranteed. Inspect the original.", "入れ子の表を線形に抽出しました。内側の行列対応は保証できないため、原文を確認してください。", language))
        if parser.truncated:
            notices.append(_tr("HTML 表格超过行列或合并跨度上限，已截断。", "An HTML table exceeded row, column, or merged-span limits and was truncated.", "HTML の表が行列または結合範囲の上限を超えたため、切り詰めました。", language))
        result = Extraction(text, "html", notices, parser.has_tables)
    elif mime == "text/plain":
        text = re.sub(r"[ \t\r\f\v]+", " ", decoded)
        result = Extraction(re.sub(r"\n\s*\n+", "\n", text).strip(), "text", notices)
    else:
        raise _error("unsupported_content", language)
    if len(result.text) > MAX_TEXT_CHARACTERS:
        result.text = table_excerpt(result, MAX_TEXT_CHARACTERS)[0] if result.has_tables else result.text[:MAX_TEXT_CHARACTERS]
        result.record_ends = [end for end in result.record_ends if end <= len(result.text)]
        result.notices.append(_tr("抽取文本超过 16,000 字符，已截断；表格末行可能不完整。", "Extracted text exceeded 16,000 characters and was truncated; the final table row may be incomplete.", "抽出テキストが 16,000 文字を超えたため、切り詰めました。表の最終行が不完全な場合があります。", language))
    return result


def _limit_pdf_worker():
    """Fail closed when the operating system cannot enforce a memory ceiling."""
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (PDF_MEMORY_BYTES, PDF_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
        return
    import ctypes
    from ctypes import wintypes
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                    ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IOCounters), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    # PROCESS_MEMORY | ACTIVE_PROCESS | KILL_ON_JOB_CLOSE: one bounded parser only.
    limits.basic.flags, limits.basic.active_processes = 0x100 | 0x8 | 0x2000, 1
    limits.process_memory = PDF_MEMORY_BYTES
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise OSError("Resource limits unavailable")
    # Keep the handle alive until process exit; closing a kill-on-close job kills it.
    globals()["_pdf_job_handle"] = job


def _pdf_worker_result(content: bytes) -> dict:
    try:
        _limit_pdf_worker()
    except Exception:
        return {"error": "pdf_resource_limit"}
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"error": "pdf_dependency_missing"}
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            return {"error": "pdf_encrypted"}
        total_pages = len(reader.pages)
        pages, text_parts, length = 0, [], 0
        truncated = total_pages > MAX_PDF_PAGES
        for page in reader.pages[:MAX_PDF_PAGES]:
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > MAX_PDF_STREAM_BYTES:
                return {"error": "pdf_resource_limit"}
            text = page.extract_text() or ""
            remaining = MAX_TEXT_CHARACTERS - length
            text_parts.append(text[:remaining])
            length += len(text[:remaining]) + 2
            pages += 1
            if len(text) > remaining or length >= MAX_TEXT_CHARACTERS:
                truncated = True
                break
        text = "\n\n".join(text_parts).strip()[:MAX_TEXT_CHARACTERS]
        if not text:
            return {"error": "pdf_no_text"}
        return {"text": text, "pages": pages, "total_pages": total_pages, "truncated": truncated}
    except MemoryError:
        return {"error": "pdf_resource_limit"}
    except Exception:
        # pypdf exceptions/logs may contain source bytes, paths, or account data.
        return {"error": "pdf_invalid"}


def _worker_main():
    import contextlib
    import logging
    logging.disable(logging.CRITICAL)
    content = sys.stdin.buffer.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        result = {"error": "document_too_large"}
    else:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = _pdf_worker_result(content)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


async def extract_pdf(content: bytes, *, language: str = "zh-CN") -> Extraction:
    if len(content) > MAX_DOCUMENT_BYTES:
        raise _error("document_too_large", language)
    process = None
    # Do not inherit application/API/source credentials into the parser process.
    worker_env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH") if name in os.environ}
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(Path(__file__).resolve()), "--pdf-worker",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=worker_env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(content), timeout=PDF_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise _error("pdf_timeout", language) from None
        if process.returncode != 0:
            raise _error("pdf_resource_limit", language)
        if len(output) > MAX_TEXT_CHARACTERS * 6 + 4096:
            raise _error("pdf_invalid", language)
        try:
            data = json.loads(output)
        except (ValueError, UnicodeError):
            raise _error("pdf_invalid", language) from None
        if not isinstance(data, dict):
            raise _error("pdf_invalid", language)
        if "error" in data:
            raise _error(data["error"] if isinstance(data["error"], str) else "pdf_invalid", language)
        if (not isinstance(data.get("text"), str) or len(data["text"]) > MAX_TEXT_CHARACTERS
                or type(data.get("pages")) is not int or not 1 <= data["pages"] <= MAX_PDF_PAGES
                or type(data.get("total_pages")) is not int or data["total_pages"] < data["pages"]
                or type(data.get("truncated")) is not bool):
            raise _error("pdf_invalid", language)
        notices = [_tr(f"PDF 文字由 pypdf 提取，已读取 {data['pages']} 页（文档共 {data['total_pages']} 页），最多读取前 12 页与 16,000 字符。本版无 OCR；阅读顺序、字体和表格排版可能影响抽取，需查看原文件。", f"pypdf extracted text from {data['pages']} of {data['total_pages']} PDF pages, limited to the first 12 pages and 16,000 characters. No OCR is performed; reading order, fonts, and table layout can affect extraction. Inspect the original file.", f"pypdf が全 {data['total_pages']} ページ中 {data['pages']} ページを抽出しました。先頭 12 ページ、16,000 文字が上限です。OCR は行いません。読み順、フォント、表のレイアウトが抽出に影響するため、元ファイルを確認してください。", language)]
        if data["truncated"]:
            notices.append(_tr("PDF 超过页数或字符预算，已截断；未抽取部分不能作为已核验资料。", "The PDF exceeded the page or character budget and was truncated. Unextracted content was not verified.", "PDF がページ数または文字数の上限を超えたため、切り詰めました。未抽出の部分は検証されていません。", language))
        return Extraction(data["text"], "pdf", notices)
    except (OSError, NotImplementedError):
        raise _error("pdf_unavailable", language) from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


async def extract_document(content: bytes, content_type: str, *, language: str = "zh-CN") -> Extraction:
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime == "application/pdf" or (mime in {"application/octet-stream", ""} and content[:1024].lstrip().startswith(b"%PDF-")):
        return await extract_pdf(content, language=language)
    return extract_text_document(content, content_type, language=language)


if __name__ == "__main__" and sys.argv[1:] == ["--pdf-worker"]:
    _worker_main()
