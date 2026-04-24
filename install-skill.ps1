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
    'references',
    'scripts',
    'templates',
    'vendor'
)

foreach ($item in $items) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $item) -Destination (Join-Path $destination $item) -Recurse -Force
}

[pscustomobject]@{
    source = $sourceRoot
    destination = $destination
    installed_items = $items
} | ConvertTo-Json -Compress
