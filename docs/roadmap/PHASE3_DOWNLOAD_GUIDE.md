# Phase 3 Corpus Download Guide

**Date:** January 22, 2026  
**Status:** Manual download instructions (automated download in progress)

---

## Download Instructions

Due to the nature of Internet Archive and other public domain repositories, some downloads require manual steps. Follow these instructions to acquire Tier 1 corpus sources.

---

## Tier 1 Sources - Download Steps

### 1. U.S. Army TM 9-803 Jeep Maintenance Manual

**URL:** https://archive.org/details/TM9803  
**Alternative URL:** https://archive.org/details/TM-9-803  
**License:** Public Domain (U.S. Government Work)  
**Domain:** `vehicle_military`

**Download Steps:**
1. Visit the Internet Archive URL above
2. Click "PDF" download button on the right sidebar
3. Save as: `data/phase3_corpus/vehicle_military/TM-9-803_Jeep_Manual.pdf`

**Alternative (command line with wget/curl):**
```bash
# Create directory
mkdir -p data/phase3_corpus/vehicle_military

# Download with wget
wget -O data/phase3_corpus/vehicle_military/TM-9-803_Jeep_Manual.pdf \
  "https://archive.org/download/TM9803/TM9803.pdf"

# Or with curl
curl -L -o data/phase3_corpus/vehicle_military/TM-9-803_Jeep_Manual.pdf \
  "https://archive.org/download/TM9803/TM9803.pdf"
```

**Expected Output:**
- File size: ~15-25 MB
- Pages: 300-400
- Estimated chunks: 700

---

### 2. Ford Model T Shop Manual (1925)

**URL:** https://archive.org/details/FordModelTShopManual  
**Alternative Search:** Search "Ford Model T service manual" on archive.org  
**License:** Public Domain (Pre-1928)  
**Domain:** `vehicle_civilian`

**Download Steps:**
1. Visit Internet Archive and search "Ford Model T service manual"
2. Look for manuals published before 1928 (public domain)
3. Download PDF version
4. Save as: `data/phase3_corpus/vehicle_civilian/Ford_Model_T_Manual.pdf`

**Alternative Sources:**
- Project Gutenberg: May have digitized automotive manuals
- Google Books: Check for full view (public domain) versions

**Expected Output:**
- File size: ~10-20 MB
- Pages: 150-250
- Estimated chunks: 400

---

### 3. Arduino Hardware Documentation

**URL:** https://docs.arduino.cc/hardware/  
**License:** Creative Commons BY-SA 3.0  
**Domain:** `hardware_electronics`

**Download Steps (Web Scraping):**

Since Arduino docs are HTML, we'll use a Python script:

```python
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# Create output directory
output_dir = Path("data/phase3_corpus/hardware_electronics")
output_dir.mkdir(parents=True, exist_ok=True)

# List of Arduino hardware pages to download
pages = [
    "https://docs.arduino.cc/hardware/uno-rev3",
    "https://docs.arduino.cc/hardware/mega-2560-rev3",
    "https://docs.arduino.cc/hardware/nano",
    "https://docs.arduino.cc/learn/starting-guide/getting-started-arduino",
]

for url in pages:
    response = requests.get(url)
    filename = url.split("/")[-1] + ".html"
    
    with open(output_dir / filename, 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    print(f"Downloaded: {filename}")
```

**Save as:** `scripts/download_arduino_docs.py` and run:
```bash
python scripts/download_arduino_docs.py
```

**Expected Output:**
- 4-6 HTML files
- Combined size: ~2-5 MB
- Estimated chunks: 300

---

### 4. Raspberry Pi GPIO Guide

**URL:** https://www.raspberrypi.com/documentation/computers/raspberry-pi.html  
**License:** Creative Commons BY-SA 4.0  
**Domain:** `hardware_electronics`

**Download Steps:**

**Option 1: Download PDF (if available):**
1. Visit https://www.raspberrypi.com/documentation/
2. Look for "Download PDF" link
3. Save as: `data/phase3_corpus/hardware_electronics/Raspberry_Pi_Documentation.pdf`

**Option 2: Web Scraping:**
```python
import requests
from pathlib import Path

output_dir = Path("data/phase3_corpus/hardware_electronics")
output_dir.mkdir(parents=True, exist_ok=True)

# Key documentation pages
pages = {
    "gpio": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
    "config": "https://www.raspberrypi.com/documentation/computers/config_txt.html",
    "os": "https://www.raspberrypi.com/documentation/computers/os.html",
}

for name, url in pages.items():
    response = requests.get(url)
    filename = f"raspberrypi_{name}.html"
    
    with open(output_dir / filename, 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    print(f"Downloaded: {filename}")
```

**Expected Output:**
- 3-4 HTML files
- Combined size: ~1-3 MB
- Estimated chunks: 150

---

### 5. OpenPLC Programming Guide

**URL:** https://www.openplcproject.com/reference/  
**License:** GPL / Open Documentation  
**Domain:** `industrial_control`

**Download Steps:**

**Option 1: Clone Git Repository:**
```bash
# Create directory
mkdir -p data/phase3_corpus/industrial_control

# Clone documentation
cd data/phase3_corpus/industrial_control
git clone https://github.com/thiagoralves/OpenPLC_v3.git
cd OpenPLC_v3/docs
```

**Option 2: Web Scraping:**
```python
import requests
from pathlib import Path

output_dir = Path("data/phase3_corpus/industrial_control")
output_dir.mkdir(parents=True, exist_ok=True)

# OpenPLC documentation pages
pages = [
    "https://www.openplcproject.com/reference/basics/",
    "https://www.openplcproject.com/reference/ladder-logic/",
    "https://www.openplcproject.com/reference/function-blocks/",
]

for url in pages:
    response = requests.get(url)
    filename = url.split("/")[-2] + ".html"
    
    with open(output_dir / filename, 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    print(f"Downloaded: {filename}")
```

**Expected Output:**
- 3-5 HTML files or markdown documents
- Combined size: ~2-4 MB
- Estimated chunks: 250

---

## Automated Download Script (PowerShell)

Save as `scripts/download_tier1_corpus.ps1`:

```powershell
# Create directory structure
$corpusDir = "data/phase3_corpus"
New-Item -ItemType Directory -Path "$corpusDir/vehicle_military" -Force | Out-Null
New-Item -ItemType Directory -Path "$corpusDir/vehicle_civilian" -Force | Out-Null
New-Item -ItemType Directory -Path "$corpusDir/hardware_electronics" -Force | Out-Null
New-Item -ItemType Directory -Path "$corpusDir/industrial_control" -Force | Out-Null

Write-Host "Created corpus directory structure" -ForegroundColor Green

# Download TM 9-803 Jeep Manual (if wget available)
if (Get-Command wget -ErrorAction SilentlyContinue) {
    Write-Host "Downloading TM 9-803 Jeep Manual..." -ForegroundColor Cyan
    wget -O "$corpusDir/vehicle_military/TM-9-803_Jeep_Manual.pdf" `
        "https://archive.org/download/TM9803/TM9803.pdf"
} else {
    Write-Host "wget not found. Please download manually from:" -ForegroundColor Yellow
    Write-Host "  https://archive.org/details/TM9803" -ForegroundColor Yellow
}

# Download Ford Model T Manual
Write-Host "`nFord Model T Manual:" -ForegroundColor Cyan
Write-Host "  Please download manually from:" -ForegroundColor Yellow
Write-Host "  https://archive.org/search.php?query=ford+model+t+manual" -ForegroundColor Yellow

# Download Arduino docs (requires Python)
if (Test-Path "scripts/download_arduino_docs.py") {
    Write-Host "`nDownloading Arduino documentation..." -ForegroundColor Cyan
    python scripts/download_arduino_docs.py
}

Write-Host "`n" + ("="*60) -ForegroundColor Green
Write-Host "Download Progress Summary" -ForegroundColor Green
Write-Host ("="*60) -ForegroundColor Green

# Check what was downloaded
$downloaded = Get-ChildItem -Path $corpusDir -Recurse -File
Write-Host "Downloaded files: $($downloaded.Count)" -ForegroundColor Cyan
foreach ($file in $downloaded) {
    $sizeMB = [math]::Round($file.Length / 1MB, 2)
    Write-Host "  - $($file.Name) ($sizeMB MB)" -ForegroundColor White
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Manually download remaining sources" -ForegroundColor White
Write-Host "2. Run validation: python scripts/validate_phase3_corpus.py" -ForegroundColor White
Write-Host "3. Ingest with hot-reload: curl -X POST http://localhost:5000/api/reload" -ForegroundColor White
```

**Run with:**
```powershell
.\scripts\download_tier1_corpus.ps1
```

---

## Validation Checklist

After downloading, validate each file:

- [ ] **File exists and is readable**
- [ ] **SHA-256 hash computed successfully**
- [ ] **PDF: Extractable text (not scanned)**
- [ ] **HTML: Valid structure, >100 chars text**
- [ ] **License file saved with source**
- [ ] **Domain tag assigned**

**Run validation:**
```bash
python scripts/validate_phase3_corpus.py
```

---

## Expected Results

### After Complete Tier 1 Download:

| Domain | Files | Total Size | Est. Chunks |
|--------|-------|------------|-------------|
| vehicle_military | 1 PDF | ~20 MB | 700 |
| vehicle_civilian | 1 PDF | ~15 MB | 400 |
| hardware_electronics | 6-8 HTML | ~5 MB | 450 |
| industrial_control | 3-5 HTML | ~3 MB | 250 |
| **TOTAL** | **11-15 files** | **~43 MB** | **~1,800** |

---

## Troubleshooting

### Issue: "wget: command not found"

**Solution (Windows):**
```powershell
# Install wget via chocolatey
choco install wget

# Or use PowerShell's Invoke-WebRequest
Invoke-WebRequest -Uri "https://archive.org/download/TM9803/TM9803.pdf" `
    -OutFile "data/phase3_corpus/vehicle_military/TM-9-803_Jeep_Manual.pdf"
```

### Issue: "PDF has no extractable text"

**Solution:** PDF is scanned, needs OCR
```bash
# Install tesseract OCR
# Windows: choco install tesseract
# Linux: apt-get install tesseract-ocr

# Run OCR
tesseract input.pdf output pdf
```

### Issue: "SSL certificate error"

**Solution:**
```bash
# wget: skip SSL verification (use cautiously)
wget --no-check-certificate -O output.pdf "URL"

# curl: skip SSL verification
curl -k -L -o output.pdf "URL"
```

---

## Next Steps (Task 9)

Once downloads are validated:

1. **Start NIC server:** `python nova_flask_app.py`
2. **Test hot-reload API:** `curl -X POST http://localhost:5000/api/reload?dry_run=true`
3. **Ingest corpus:** `curl -X POST http://localhost:5000/api/reload`
4. **Verify chunks:** Check `vector_db/corpus_manifest.json`

---

**Status:** Ready for manual download + validation ✅

*Last updated: January 22, 2026*
