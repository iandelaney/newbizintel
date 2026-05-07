param(
    [string]$OutputRoot,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = & (Join-Path $PSScriptRoot '..\common\resolve_output_root.ps1')
}

$resolvedOutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$forbiddenNames = @('skill-runs', 'vercel')
$forbidden = @()

foreach ($name in $forbiddenNames) {
    $candidate = Join-Path $resolvedOutputRoot $name
    if (Test-Path -LiteralPath $candidate) {
        $forbidden += [pscustomobject]@{
            name = $name
            path = $candidate
            reason = 'Proof or handoff artifacts should not live as sibling folders in the delivery output root.'
        }
    }
}

$warnings = @()
if ($forbidden.Count -gt 0) {
    $warnings += ("Output root contains non-canonical NewBizIntel sibling artifact folders: {0}" -f (@($forbidden | ForEach-Object { $_.name }) -join ', '))
}

$ok = -not ($Strict -and $forbidden.Count -gt 0)

[pscustomobject]@{
    ok = $ok
    output_root = $resolvedOutputRoot
    strict = [bool]$Strict
    forbidden_count = $forbidden.Count
    forbidden = $forbidden
    warnings = $warnings
    errors = if ($ok) { @() } else { $warnings }
} | ConvertTo-Json -Depth 6
