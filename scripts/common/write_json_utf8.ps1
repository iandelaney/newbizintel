param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [object]$InputObject
)

$ErrorActionPreference = 'Stop'

$directory = Split-Path -Parent $Path
if ($directory) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$json = $InputObject | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
