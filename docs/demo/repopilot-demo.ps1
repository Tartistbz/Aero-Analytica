$ErrorActionPreference = "Stop"

Write-Host "[1/3] Running deterministic smoke evaluation..." -ForegroundColor Cyan
npm run eval:smoke -- --report .repopilot/reports/demo.html

Write-Host "[2/3] Running the full 15-task robotics suite..." -ForegroundColor Cyan
npm run eval:robotics -- --report .repopilot/reports/robotics-15.html

$tempRoot = [System.IO.Path]::GetTempPath()
$latestRun = Get-ChildItem -Path $tempRoot -Directory -Recurse -ErrorAction Stop |
  Where-Object { $_.Parent.Name -eq "runs" -and $_.Name -match "^[0-9a-f-]{36}$" } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($null -eq $latestRun) {
  throw "No RepoPilot run artifact was created."
}

Write-Host "[3/3] Replaying the latest run without a model or shell..." -ForegroundColor Cyan
npm run repopilot -- replay --run $latestRun.FullName

Write-Host "Demo artifacts:" -ForegroundColor Green
Write-Host "  $((Resolve-Path '.repopilot\reports\demo.html').Path)"
Write-Host "  $((Resolve-Path '.repopilot\reports\robotics-15.html').Path)"
