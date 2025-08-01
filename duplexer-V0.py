# api/duplexer.py
from io import BytesIO
from flask import Flask, request, send_file, abort
from PyPDF2 import PdfReader, PdfWriter

app = Flask(__name__)

@app.route("/api/duplexer", methods=["POST"])
def duplex_endpoint():
    # 1) Validate upload
    if "file" not in request.files:
        return abort(400, "Missing file field")
    upload = request.files["file"]
    if upload.filename == "":
        return abort(400, "No file selected")

    # 2) Read & duplex in memory
    data = upload.read()
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)     # front
        writer.add_page(page)     # back

    out_io = BytesIO()
    writer.write(out_io)
    out_io.seek(0)

    # 3) Send it back with a download prompt
    return send_file(
        out_io,
        as_attachment=True,
        download_name=f"duplex_{upload.filename}",
        mimetype="application/pdf"
    )

# Vercel will pick up `app` as the WSGI entrypoint
