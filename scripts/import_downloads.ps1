# Copy manuals from Downloads to Phase 3 corpus
# Automatically categorizes by filename patterns and copies to appropriate domains

$downloadsPath = "C:\Users\draku\Downloads"
$corpusPath = "data/phase3_corpus"

Write-Host "=== Phase 3 Corpus Import ===" -ForegroundColor Cyan
Write-Host ""

# Ensure corpus directories exist
$domains = @("vehicle_military", "vehicle_civilian", "hardware_electronics", "industrial_control")
foreach ($domain in $domains) {
    $domainPath = Join-Path $corpusPath $domain
    if (-not (Test-Path $domainPath)) {
        New-Item -ItemType Directory -Path $domainPath -Force | Out-Null
        Write-Host "Created: $domain/" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Scanning Downloads folder..." -ForegroundColor Yellow

# Find PDF files
$pdfFiles = Get-ChildItem $downloadsPath -File -Filter "*.pdf" -ErrorAction SilentlyContinue

if ($pdfFiles) {
    Write-Host "Found $($pdfFiles.Count) PDF file(s):" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($file in $pdfFiles) {
        $sizeMB = [math]::Round($file.Length / 1MB, 2)
        $name = $file.Name.ToLower()
        
        # Determine domain based on filename
        $targetDomain = "vehicle_civilian"  # default
        
        if ($name -match "tm-?9|jeep|military|army|m998|hmmwv|tactical") {
            $targetDomain = "vehicle_military"
        }
        elseif ($name -match "model\s*t|ford|chevrolet|volkswagen|beetle") {
            $targetDomain = "vehicle_civilian"
        }
        elseif ($name -match "arduino|raspberry|rpi|microcontroller|gpio") {
            $targetDomain = "hardware_electronics"
        }
        elseif ($name -match "plc|ladder|industrial|control|automation") {
            $targetDomain = "industrial_control"
        }
        
        $destination = Join-Path (Join-Path $corpusPath $targetDomain) $file.Name
        
        Write-Host "  $($file.Name)" -ForegroundColor White
        Write-Host "    Size: $sizeMB MB" -ForegroundColor Gray
        Write-Host "    Domain: $targetDomain" -ForegroundColor Yellow
        
        # Copy file
        try {
            Copy-Item -Path $file.FullName -Destination $destination -Force
            Write-Host "    Status: Copied ✓" -ForegroundColor Green
        }
        catch {
            Write-Host "    Status: Failed - $_" -ForegroundColor Red
        }
        
        Write-Host ""
    }
}
else {
    Write-Host "No PDF files found in Downloads" -ForegroundColor Yellow
}

# Check for HTML files
$htmlFiles = Get-ChildItem $downloadsPath -File | Where-Object { $_.Extension -in @('.html', '.htm') } | Select-Object -First 10

if ($htmlFiles) {
    Write-Host "Found $($htmlFiles.Count) HTML file(s):" -ForegroundColor Cyan
    
    foreach ($file in $htmlFiles) {
        $sizeMB = [math]::Round($file.Length / 1MB, 2)
        $targetDomain = "hardware_electronics"  # Most HTML docs are hardware
        $destination = Join-Path (Join-Path $corpusPath $targetDomain) $file.Name
        
        Write-Host "  $($file.Name) - $sizeMB MB → $targetDomain" -ForegroundColor Gray
        Copy-Item -Path $file.FullName -Destination $destination -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== Import Summary ===" -ForegroundColor Cyan

# Show what was imported
foreach ($domain in $domains) {
    $domainPath = Join-Path $corpusPath $domain
    $files = Get-ChildItem $domainPath -File -ErrorAction SilentlyContinue
    
    if ($files) {
        $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
        $totalMB = [math]::Round($totalSize / 1MB, 2)
        
        Write-Host "`n$domain/:" -ForegroundColor Yellow
        Write-Host "  Files: $($files.Count)" -ForegroundColor White
        Write-Host "  Size: $totalMB MB" -ForegroundColor White
        
        $files | ForEach-Object {
            $fileMB = [math]::Round($_.Length / 1MB, 2)
            Write-Host "    - $($_.Name) ($fileMB MB)" -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Validate: python scripts/validate_phase3_corpus.py" -ForegroundColor White
Write-Host "2. Start server: python nova_flask_app.py" -ForegroundColor White
Write-Host "3. Hot-reload: curl -X POST http://localhost:5000/api/reload" -ForegroundColor White
