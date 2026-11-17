param([Parameter(Mandatory=$true)][string]$RunId)

$script:fails = 0
function Check($name, $ok) {
  if ($ok) { Write-Host "PASS  $name" -ForegroundColor Green }
  else     { Write-Host "FAIL  $name" -ForegroundColor Red; $script:fails++ }
}

# 1. WeasyPrint
python -c "from weasyprint import HTML; HTML(string='<h1>hi</h1>').write_pdf('_t.pdf')" 2>$null
Check "1 WeasyPrint renders a PDF" (Test-Path _t.pdf)
Remove-Item _t.pdf -ErrorAction SilentlyContinue

# 2. Data layer
Check "2 reporting/stats.py exists" (Test-Path src\audit\reporting\stats.py)
Check "2 reporting/pdf.py exists"   (Test-Path src\audit\reporting\pdf.py)

# 3. Template
$tpl = Get-ChildItem -Recurse -Filter report.html.j2 | Select-Object -First 1
Check "3 report.html.j2 exists" ($null -ne $tpl)
if ($tpl) {
  $t = Get-Content $tpl.FullName -Raw
  foreach ($s in "Executive summary","Methodology","Limitations","Cost","Failure","Fixes","Calibration") {
    Check "3 template mentions '$s'" ($t -match $s)
  }
}
Check "3 autoescape=True in code" (Select-String -Path src\audit\reporting\*.py -Pattern "autoescape\s*=\s*True" -Quiet)

# 5. CLI
New-Item -ItemType Directory -Force out | Out-Null
Remove-Item out\_check.pdf -ErrorAction SilentlyContinue
audit report --run $RunId --out out\_check.pdf 2>&1 | Out-Null
Check "5 'audit report' produced a PDF" ((Test-Path out\_check.pdf) -and ((Get-Item out\_check.pdf).Length -gt 5000))

# 6/7. PDF content
python check_day8_pdf.py

# 7. Sample report + tests
Check "7 examples/sample_report.pdf exists" (Test-Path examples\sample_report.pdf)
pytest -q 2>&1 | Out-Null
Check "pytest passes" ($LASTEXITCODE -eq 0)

Write-Host ""
Write-Host "$($script:fails) failed check(s)." -ForegroundColor Yellow
Write-Host "Still check by eye: print preview, no private data, table layout."
