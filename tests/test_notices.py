import base64
import importlib.util
import io
import unittest
from unittest.mock import Mock, patch

from wemust.client import WeMustError
from wemust.notices import NoticeReader, validate_file_url


class TestNotices(unittest.TestCase):
    def test_blocked_attachment_url_is_never_requested(self):
        c = Mock()
        c.api.return_value = (
            200,
            {
                "model": {
                    "id": 1,
                    "attachments": [
                        {
                            "id": 7,
                            "fileExt": "pdf",
                            "fileUrl": "https://other.test/private",
                        }
                    ],
                }
            },
        )
        with patch("wemust.notices.build_opener") as opener:
            with self.assertRaises(WeMustError):
                NoticeReader(c).attachment_pdf(1, 7)
            opener.assert_not_called()

    def test_redirect_cannot_leave_school_file_hosts(self):
        from wemust.notices import SchoolRedirects

        with self.assertRaises(WeMustError):
            SchoolRedirects().redirect_request(
                Mock(), None, 302, "Found", {}, "https://other.test/a"
            )

    def test_non_pdf_response_is_rejected(self):
        c = Mock()
        c.api.return_value = (
            200,
            {
                "model": {
                    "id": 1,
                    "attachments": [
                        {
                            "id": 7,
                            "fileExt": "pdf",
                            "fileUrl": "https://wm-fs.must.edu.mo/a.pdf",
                        }
                    ],
                }
            },
        )
        response = Mock()
        response.geturl.return_value = "https://wm-fs.must.edu.mo/a.pdf"
        response.read.return_value = b"<html>login required</html>"
        with patch("wemust.notices.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = response
            with self.assertRaisesRegex(WeMustError, "not a PDF"):
                NoticeReader(c).attachment_pdf(1, 7)

    @unittest.skipUnless(
        importlib.util.find_spec("pypdf"), "optional pypdf not installed"
    )
    def test_blank_pdf_reports_needs_ocr(self):
        from pypdf import PdfWriter

        stream = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.write(stream)
        r = NoticeReader(Mock())
        r.attachment_pdf = Mock(
            return_value=({"fileName": "synthetic.pdf"}, stream.getvalue())
        )
        result = r.attachment_text(1, 7)
        self.assertTrue(result["needs_ocr"])
        self.assertEqual(result["total_pages"], 1)
        self.assertFalse(result["truncated"])

    @unittest.skipUnless(
        importlib.util.find_spec("pymupdf"), "optional PyMuPDF not installed"
    )
    def test_render_synthetic_pdf_as_png_and_check_page_bounds(self):
        import pymupdf

        with pymupdf.open() as doc:
            doc.new_page(width=200, height=300).insert_text(
                (20, 30), "Synthetic notice"
            )
            data = doc.tobytes()
        r = NoticeReader(Mock())
        r.attachment_pdf = Mock(return_value=({"fileName": "synthetic.pdf"}, data))
        result = r.attachment_page(1, 7, 1)
        self.assertEqual(result["content"][1]["mimeType"], "image/png")
        self.assertTrue(
            base64.b64decode(result["content"][1]["data"]).startswith(b"\x89PNG")
        )
        with self.assertRaises(WeMustError):
            r.attachment_page(1, 7, 2)

    def test_page_tool_preserves_native_image_content(self):
        from wemust.mcp_server import handle

        result = {
            "content": [
                {"type": "image", "mimeType": "image/png", "data": "image-data"}
            ],
            "isError": False,
        }
        with patch("wemust.mcp_server._call_tool", return_value=result):
            response = handle(
                {
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_notice_attachment_page", "arguments": {}},
                },
                Mock(),
            )
        self.assertEqual(response["result"]["content"][0]["type"], "image")

    def test_detail_is_not_snippet_and_omits_signed_urls(self):
        c = Mock()
        c.api.return_value = (
            200,
            {
                "model": {
                    "id": 1,
                    "content": "<p>" + "a" * 200 + "</p>",
                    "attachments": [
                        {"id": 3, "fileName": "file.pdf", "fileUrl": "secret"}
                    ],
                }
            },
        )
        d = NoticeReader(c).detail(1)
        self.assertEqual(len(d["content"]), 200)
        self.assertNotIn("fileUrl", d["attachments"][0])

    def test_wrong_notice_response_rejected(self):
        c = Mock()
        c.api.return_value = (200, {"model": {"id": 2}})
        with self.assertRaises(WeMustError):
            NoticeReader(c).detail(1)

    def test_attachment_must_belong_to_notice(self):
        c = Mock()
        c.api.return_value = (200, {"model": {"id": 1, "attachments": []}})
        with self.assertRaises(WeMustError):
            NoticeReader(c).attachment_text(1, 7)

    def test_file_hosts_and_protocol_restricted(self):
        validate_file_url("https://wm-fs.must.edu.mo/group/file.pdf?token=secret")
        for url in (
            "http://wm-fs.must.edu.mo/a",
            "https://evil.test/a",
            "https://wm-fs.must.edu.mo.evil.test/a",
            "https://user@wm-fs.must.edu.mo/a",
        ):
            with self.assertRaises(WeMustError):
                validate_file_url(url)
