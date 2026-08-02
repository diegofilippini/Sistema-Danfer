param(
    [string]$Destination = "..\outputs\Sistema-Danfer-Industrial-OS-1.5.0.zip"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$destinationPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $Destination))
$stagingRoot = Join-Path $projectRoot "work\release-staging"
$packageRoot = Join-Path $stagingRoot "Sistema-Danfer-Industrial-OS-1.5.0"

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

$included = @(
    "src", "tests", "scripts", "README.md", "LEIA-ME-WINDOWS.txt",
    "DOCUMENTACAO_OPERACIONAL.md", "MATRIZ_CONSOLIDACAO.md",
    "INICIAR_WEB.bat", "pyproject.toml", ".gitignore"
)
foreach ($item in $included) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $item) -Destination $packageRoot -Recurse -Force
}

Get-ChildItem -LiteralPath $packageRoot -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $packageRoot -Recurse -File |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force
Get-ChildItem -LiteralPath $packageRoot -Recurse -Directory -Filter "*.egg-info" |
    Remove-Item -Recurse -Force

$destinationDir = Split-Path -Parent $destinationPath
New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
if (Test-Path -LiteralPath $destinationPath) {
    Remove-Item -LiteralPath $destinationPath -Force
}
Compress-Archive -LiteralPath $packageRoot -DestinationPath $destinationPath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
Write-Output "Pacote: $destinationPath"
Write-Output "SHA256: $hash"
