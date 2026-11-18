FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

# LibreOffice (Word -> PDF), OCRmyPDF + Tesseract (scanned PDFs, English + Sinhala),
# and metric-compatible fonts so layouts match Word (Calibri/Cambria/Arial/Times).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer libreoffice-core \
      ocrmypdf tesseract-ocr tesseract-ocr-eng tesseract-ocr-sin ghostscript \
      fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea \
      fonts-dejavu fonts-noto-core \
    && rm -rf /var/lib/apt/lists/* && fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300
