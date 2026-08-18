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
$ragNetworkDefinition = $config.networks.PSObject.Properties | Where-Object { $_.Name -eq "rag" } | Select-Object -First 1
if ($null -ne $ragNetworkDefinition -and $ragNetworkDefinition.Value.external) {
  $ragNetworkName = [string]$ragNetworkDefinition.Value.name
  docker network inspect $ragNetworkName *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "External RAG network '$ragNetworkName' is missing. Start the generated RAG overlay first."
  }
}
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
docker compose @composeArgs build
if ($LASTEXITCODE -ne 0) { throw "Docker Compose image build failed." }
if ($null -ne $ragNetworkDefinition -and $ragNetworkDefinition.Value.external) {
  $ragPreflight = @'
from urllib.request import urlopen
import os
urlopen(os.environ["RAG_SEARCH_URL"] + "/_cluster/health", timeout=5).read()
urlopen(os.environ["RAG_OLLAMA_URL"] + "/api/tags", timeout=5).read()
'@
  docker compose @composeArgs run --rm --no-deps --no-TTY --entrypoint python application -c $ragPreflight
  if ($LASTEXITCODE -ne 0) {
    throw "RAG endpoints are unavailable. Start the generated RAG overlay and inference profile first."
  }
}
docker compose @composeArgs up -d --wait
