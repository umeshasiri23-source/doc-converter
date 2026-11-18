import io
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

OCR_LANGS = os.environ.get("OCR_LANGS", "eng+sin")
SOFFICE_TIMEOUT = int(os.environ.get("SOFFICE_TIMEOUT", "120"))
OCR_TIMEOUT = int(os.environ.get("OCR_TIMEOUT", "240"))
slots = threading.BoundedSemaphore(int(os.environ.get("CONVERSION_SLOTS", "2")))


class ConversionError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def read_upload(allowed_ext):
    f = request.files.get("file")
    if not f or not f.filename:
        raise ConversionError("No file received. Choose a file and try again.", 400)
    ext = Path(f.filename).suffix.lower()
    if ext not in allowed_ext:
        raise ConversionError(
            f"This tool accepts {', '.join(sorted(allowed_ext))} files. You sent {ext or 'a file with no extension'}.", 400
        )
    return f, ext


def check_magic(path, ext):
    head = path.read_bytes()[:8]
    ok = {
        ".pdf": head.startswith(b"%PDF"),
        ".docx": head.startswith(b"PK"),
        ".doc": head.startswith(b"\xd0\xcf\x11\xe0"),
    }[ext]
    if not ok:
        raise ConversionError(f"The file is not a valid {ext} document. It may be corrupted or renamed.", 400)


def word_to_pdf(src: Path, workdir: Path) -> Path:
    profile = workdir / "lo-profile"
    cmd = [
        "soffice",
        f"-env:UserInstallation=file://{profile}",
        "--headless", "--norestore", "--nolockcheck",
        "--convert-to", "pdf:writer_pdf_Export",
        "--outdir", str(workdir),
        str(src),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=SOFFICE_TIMEOUT,
                       env={**os.environ, "HOME": str(workdir)})
    except subprocess.TimeoutExpired:
        raise ConversionError("Conversion took too long. Try a smaller document.", 504)
    except subprocess.CalledProcessError:
        raise ConversionError("The document could not be converted. It may be password-protected or damaged.")
    out = workdir / (src.stem + ".pdf")
    if not out.exists():
        raise ConversionError("The document could not be converted.")
    return out


def pdf_needs_ocr(pdf: Path) -> bool:
    try:
        import fitz  # PyMuPDF, installed with pdf2docx
    except ImportError:
        return False
    doc = fitz.open(pdf)
    if doc.needs_pass:
        raise ConversionError("This PDF is password-protected. Remove the password first.")
    pages = min(len(doc), 5)
    chars = sum(len(doc[i].get_text("text").strip()) for i in range(pages))
    doc.close()
    return pages > 0 and chars / pages < 20


def pdf_to_word(src: Path, workdir: Path) -> Path:
    pdf = src
    if pdf_needs_ocr(src):
        ocr_out = workdir / "ocr.pdf"
        try:
            subprocess.run(
                ["ocrmypdf", "--skip-text", "--optimize", "0", "-l", OCR_LANGS, str(src), str(ocr_out)],
                check=True, capture_output=True, timeout=OCR_TIMEOUT,
            )
            pdf = ocr_out
        except subprocess.TimeoutExpired:
            raise ConversionError("This scanned PDF took too long to read. Try fewer pages.", 504)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ConversionError("This looks like a scanned PDF and text recognition failed.")
    from pdf2docx import Converter

    out = workdir / (src.stem + ".docx")
    try:
        cv = Converter(str(pdf))
        cv.convert(str(out))
        cv.close()
    except Exception:
        raise ConversionError("The PDF could not be converted. It may be damaged.")
    return out


def run_conversion(allowed_ext, convert, mimetype, out_ext):
    try:
        f, ext = read_upload(allowed_ext)
        if not slots.acquire(timeout=60):
            raise ConversionError("The server is busy. Try again in a minute.", 503)
        workdir = Path(tempfile.mkdtemp(prefix="conv-"))
        try:
            src = workdir / f"{uuid.uuid4().hex}{ext}"
            f.save(src)
            check_magic(src, ext)
            out = convert(src, workdir)
            data = io.BytesIO(out.read_bytes())
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            slots.release()
        name = Path(f.filename).stem + out_ext
        return send_file(data, mimetype=mimetype, as_attachment=True, download_name=name)
    except ConversionError as e:
        return jsonify(error=str(e)), e.status


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/convert/word-to-pdf")
def convert_word_to_pdf():
    return run_conversion({".docx", ".doc"}, word_to_pdf, "application/pdf", ".pdf")


@app.post("/convert/pdf-to-word")
def convert_pdf_to_word():
    return run_conversion(
        {".pdf"}, pdf_to_word,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx",
    )


@app.errorhandler(413)
def too_large(_):
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify(error=f"File is larger than {mb} MB."), 413


if __name__ == "__main__":
    app.run(debug=True, port=5000)
