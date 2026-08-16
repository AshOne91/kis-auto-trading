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

$composeArgs = @(
  "--env-file", "environment\.env",
  "--env-file", "deploy\single-host\runtime.env",
  "-f", "environment\compose.integration.yml",
  "-f", "deploy\single-host\compose.override.yml"
)
$composeConfig = docker compose @composeArgs config --format json
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }
$config = $composeConfig | ConvertFrom-Json
$published = @{}
foreach ($service in $config.services.PSObject.Properties) {
  foreach ($port in @($service.Value.ports)) {
    if ($null -eq $port.published) { continue }
    $publishedPort = [int]$port.published
    if ($published.ContainsKey($publishedPort)) {
      throw "Published host port collision: $publishedPort ($($published[$publishedPort]) and $($service.Name))"
    }
    $published[$publishedPort] = $service.Name
  }
}

$env:COMPOSE_IGNORE_ORPHANS = "true"
docker compose @composeArgs up -d --wait
