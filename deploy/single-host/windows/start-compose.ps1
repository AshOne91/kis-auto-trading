$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $ProjectRoot

docker compose `
  --env-file environment\.env `
  --env-file deploy\single-host\runtime.env `
  -f environment\compose.integration.yml `
  -f deploy\single-host\compose.override.yml `
  up -d --wait
