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
    'bootstrap-runtime.ps1',
    'bootstrap-runtime.sh',
    'package.json',
    'package-lock.json',
    'README.md',
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

$runtimeBootstrapped = $false
$runtimeCheck = Join-Path $destination 'scripts\qa\check_python_runtime.py'
$runtimeBootstrap = Join-Path $destination 'scripts\bootstrap_vendor_runtime.py'
if (Test-Path -LiteralPath $runtimeCheck) {
    $python = & (Join-Path $sourceRoot 'scripts\common\resolve_python.ps1')
    & $python $runtimeCheck --repo-root $destination --runtime-only --quiet
    if ($LASTEXITCODE -ne 0) {
        & $python $runtimeBootstrap --repo-root $destination | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Python runtime bootstrap failed with exit code $LASTEXITCODE."
        }
        $runtimeBootstrapped = $true
    }
}

[pscustomobject]@{
    source = $sourceRoot
    destination = $destination
    installed_items = $installedItems
    skipped_missing_items = $skippedItems
    python_runtime_bootstrapped = $runtimeBootstrapped
} | ConvertTo-Json -Compress
