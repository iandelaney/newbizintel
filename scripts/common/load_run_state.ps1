param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    throw "Run-state file not found: $Path"
}

Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
