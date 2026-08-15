$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $ProjectRoot

$deadline = (Get-Date).AddMinutes(5)
do {
  docker info *> $null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)
if ($LASTEXITCODE -ne 0) { throw "Docker engine did not become ready within 5 minutes." }

docker compose `
  --env-file environment\.env `
  --env-file deploy\single-host\runtime.env `
  -f environment\compose.integration.yml `
  -f deploy\single-host\compose.override.yml `
  up -d --wait
