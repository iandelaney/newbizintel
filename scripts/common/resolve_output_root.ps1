param(
    [string]$ExplicitRoot,
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'

if ($ExplicitRoot) {
    return [System.IO.Path]::GetFullPath($ExplicitRoot)
}

if ($env:NEWBIZINTEL_OUTPUT_ROOT) {
    return [System.IO.Path]::GetFullPath($env:NEWBIZINTEL_OUTPUT_ROOT)
}

if ($env:NEWBIZ2_OUTPUT_ROOT) {
    return [System.IO.Path]::GetFullPath($env:NEWBIZ2_OUTPUT_ROOT)
}

$cwdOutput = Join-Path (Get-Location).Path 'output'
if (Test-Path -LiteralPath $cwdOutput) {
    return [System.IO.Path]::GetFullPath($cwdOutput)
}

$workspaceOutput = 'C:\codex projects\output'
if (Test-Path -LiteralPath $workspaceOutput) {
    return [System.IO.Path]::GetFullPath($workspaceOutput)
}

return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'output'))
