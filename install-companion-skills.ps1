param(
    [string]$DestinationRoot = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$sourceRoot = Join-Path $PSScriptRoot 'companion-skills'
if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "No companion-skills folder found at $sourceRoot"
}

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

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

$installed = @()
$skipped = @()

Get-ChildItem -LiteralPath $sourceRoot -Directory | ForEach-Object {
    $skillName = $_.Name
    $destination = Join-Path $DestinationRoot $skillName

    if ((Test-Path -LiteralPath $destination) -and -not $Force) {
        $skipped += $skillName
        return
    }

    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }

    Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    $installed += $skillName
}

[pscustomobject]@{
    source = $sourceRoot
    destination_root = $DestinationRoot
    force = [bool]$Force
    installed_skills = $installed
    skipped_existing_skills = $skipped
} | ConvertTo-Json -Depth 5 -Compress
