# Word <-> PDF converter

Flask backend, one HTML page, Docker for deployment.

- Word -> PDF: LibreOffice headless (with Carlito/Caladea/Liberation fonts so layouts match Word)
- PDF -> Word: pdf2docx; scanned PDFs are OCR'd first with OCRmyPDF + Tesseract (English + Sinhala)

## Run with Docker (recommended)
    docker build -t doc-converter .
    docker run -p 8000:8000 doc-converter
Open http://localhost:8000

## Run without Docker (Ubuntu/Debian)
    sudo apt install libreoffice-writer ocrmypdf tesseract-ocr tesseract-ocr-sin fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    python app.py

## Settings (environment variables)
MAX_UPLOAD_MB (50), CONVERSION_SLOTS (2), OCR_LANGS (eng+sin), SOFFICE_TIMEOUT (120), OCR_TIMEOUT (240)

## Deploy
Any host that runs Docker works (Render, Railway, Fly.io, a VPS). Give it at least 1 GB RAM:
LibreOffice and OCR are heavy and a 512 MB instance will often crash.
Add a rate limit (e.g. Cloudflare or flask-limiter) before making it public.
