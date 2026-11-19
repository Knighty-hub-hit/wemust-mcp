# Notice details and PDF attachments

`get_notice_detail(notice_id)` uses the signed, authenticated GET endpoint used by
the school's detail page: `/x-info-portal-api/article-portals/{id}`. It returns body
text and attachment metadata without signed download URLs.

`get_notice_attachment_text(notice_id, attachment_id)` obtains a fresh signed URL
from that notice, downloads the PDF into memory, and extracts page-numbered text.
Only HTTPS on `wm-fs.must.edu.mo` and `wm-fs2.must.edu.mo` is accepted, including
redirects. Limits: 10 MiB, 100 pages, 80,000 characters. Scan-only PDFs report
`needs_ocr`; table alignment must be checked visually. Attachment contents are
sent to the connected AI client when this tool is called. No file is saved.

PDF extraction uses the optional `pdf` extra: `python -m pip install ".[pdf]"`.
Restart your MCP client after server changes to refresh tools. The original
`get_notices` remains a short summary. Basic notice details do not need PDF libraries.

`get_notice_attachment_page(notice_id, attachment_id, page=1)` renders one PDF page
as an MCP image content block, suitable for scanned notices and table verification.
It uses the optional `pdf-images` extra (`python -m pip install ".[pdf-images]"`,
Python 3.10+), keeps data in memory, and caps the longer
image dimension at 2200 pixels. This does not run an OCR service or save images.

PyMuPDF is distributed under AGPL/commercial licensing; review its upstream
license before choosing the image-rendering extra. The basic and text-only
features do not import PyMuPDF. See https://github.com/pymupdf/PyMuPDF/blob/main/COPYING.
