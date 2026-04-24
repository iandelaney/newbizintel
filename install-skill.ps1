param(
    [string]$DestinationRoot = ''
)

$ErrorActionPreference = 'Stop'

if (-not $DestinationRoot) {
    if ($env:CODEX_HOME) {
        $DestinationRoot = Join-Path $env:CODEX_HOME 'skills'
    }
    elseif ($env:HOME) {
        $DestinationRoot = Join-Path $env:HOME '.codex/skills'
    }
    else {
        $DestinationRoot = Join-Path $env:USERPROFILE '.codex\skills'
    }
}

$sourceRoot = $PSScriptRoot
$destination = Join-Path $DestinationRoot 'newbiz2'

if (Test-Path -LiteralPath $destination) {
    Remove-Item -LiteralPath $destination -Recurse -Force
}

New-Item -ItemType Directory -Path $destination | Out-Null

$items = @(
    'SKILL.md',
    'agents',
    'assets',
    'package.json',
    'package-lock.json',
    'references',
    'scripts',
    'templates',
    'vendor'
)

$installedItems = @()
$skippedItems = @()

foreach ($item in $items) {
    $sourcePath = Join-Path $sourceRoot $item
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        $skippedItems += $item
        continue
    }

    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $destination $item) -Recurse -Force
    $installedItems += $item
}

if (Test-Path -LiteralPath (Join-Path $destination 'package.json')) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw 'Node.js and npm are required to install the native PPTX export dependency.'
    }
    Push-Location $destination
    try {
        & $npm.Source install --omit=dev | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

[pscustomobject]@{
    source = $sourceRoot
    destination = $destination
    installed_items = $installedItems
    skipped_missing_items = $skippedItems
} | ConvertTo-Json -Compress
