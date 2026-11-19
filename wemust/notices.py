"""Authenticated notice details and bounded, in-memory PDF attachment reading."""

import base64
import io
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, build_opener

from .client import WeMustError, _strip_html

FILE_HOSTS = {"wm-fs.must.edu.mo", "wm-fs2.must.edu.mo"}


def validate_file_url(url):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in FILE_HOSTS
        or p.port not in (None, 443)
        or p.username
        or p.password
    ):
        raise WeMustError("Attachment URL is not on an allowed school file server.")


class SchoolRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_file_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoticeReader:
    def __init__(self, client):
        self.client = client

    def record(self, notice_id):
        notice_id = int(notice_id)
        if notice_id <= 0:
            raise WeMustError("notice_id must be positive.")
        self.client.login()
        status, body = self.client.api(
            "/x-info-portal-api", "/article-portals/" + str(notice_id), "wm-info-portal"
        )
        model = body.get("model") if isinstance(body, dict) else None
        if (
            status != 200
            or not isinstance(model, dict)
            or str(model.get("id")) != str(notice_id)
        ):
            raise WeMustError(
                "Notice detail is unavailable or not accessible to this account."
            )
        return model

    def detail(self, notice_id):
        a = self.record(notice_id)
        text = _strip_html(a.get("content"))
        return {
            "id": a["id"],
            "title": a.get("title"),
            "source": a.get("sourceGroupName"),
            "date": a.get("postDate"),
            "content": text[:80000],
            "truncated": len(text) > 80000,
            "attachments": [
                {k: f.get(k) for k in ("id", "fileName", "fileExt", "fileSize")}
                for f in a.get("attachments") or []
            ],
            "note": "Empty body may mean the information is in attachments. Use get_notice_attachment_text for PDFs.",
        }

    def attachment_pdf(self, notice_id, attachment_id):
        a = self.record(notice_id)
        f = next(
            (
                f
                for f in a.get("attachments") or []
                if str(f.get("id")) == str(int(attachment_id))
            ),
            None,
        )
        if f is None:
            raise WeMustError("Attachment does not belong to this accessible notice.")
        if str(f.get("fileExt", "")).lower() != "pdf":
            raise WeMustError(
                "Text extraction currently supports PDF attachments only."
            )
        url = f.get("fileUrl") or ""
        validate_file_url(url)
        op = build_opener(SchoolRedirects(), HTTPCookieProcessor(self.client.cj))
        try:
            with op.open(url, timeout=30) as r:
                validate_file_url(r.geturl())
                data = r.read(10 * 1024 * 1024 + 1)
        except Exception:
            raise WeMustError(
                "Attachment download failed; signed URLs may expire. No URL or token is logged."
            ) from None
        if len(data) > 10 * 1024 * 1024:
            raise WeMustError("PDF exceeds the 10 MiB read limit.")
        if not data.startswith(b"%PDF-"):
            raise WeMustError("Attachment response is not a PDF.")
        return f, data

    def attachment_page(self, notice_id, attachment_id, page=1):
        page = int(page)
        if page < 1:
            raise WeMustError("page must be at least 1.")
        f, data = self.attachment_pdf(notice_id, attachment_id)
        if sys.version_info < (3, 10):
            raise WeMustError("PDF page images require Python 3.10 or newer.")
        try:
            import pymupdf
        except ImportError:
            raise WeMustError(
                'PDF page renderer is not installed. Run: python -m pip install ".[pdf-images]"'
            ) from None
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if page > len(doc):
                raise WeMustError("page exceeds PDF page count.")
            p = doc[page - 1]
            scale = min(2, 2200 / max(p.rect.width, p.rect.height))
            pix = p.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f["fileName"]
                        + " - page "
                        + str(page)
                        + "/"
                        + str(len(doc)),
                    },
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": base64.b64encode(pix.tobytes("png")).decode("ascii"),
                    },
                ],
                "isError": False,
            }

    def attachment_text(self, notice_id, attachment_id):
        f, data = self.attachment_pdf(notice_id, attachment_id)
        try:
            from pypdf import PdfReader
        except ImportError:
            raise WeMustError(
                'PDF text reader is not installed. Run: python -m pip install ".[pdf]"'
            ) from None
        reader = PdfReader(io.BytesIO(data))
        pages, chars = [], 0
        for i, page in enumerate(reader.pages):
            if i >= 100 or chars >= 80000:
                break
            text = page.extract_text() or ""
            pages.append({"page": i + 1, "text": text[: 80000 - chars]})
            chars += len(text)
        return {
            "notice_id": int(notice_id),
            "attachment_id": int(attachment_id),
            "file_name": f.get("fileName"),
            "total_pages": len(reader.pages),
            "pages": pages,
            "truncated": len(pages) < len(reader.pages) or chars > 80000,
            "needs_ocr": not any(p["text"].strip() for p in pages),
            "note": "PDF text extraction only; table alignment and image-only text require visual verification.",
        }
