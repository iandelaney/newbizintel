param(
    [string]$ProofRoot,
    [switch]$NoCreate
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ProofRoot)) {
    $ProofRoot = $env:NEWBIZINTEL_PROOF_ROOT
}

$outputRoot = & (Join-Path $PSScriptRoot 'resolve_output_root.ps1')
$workspaceRoot = Split-Path -Parent $outputRoot

if ([string]::IsNullOrWhiteSpace($ProofRoot)) {
    $ProofRoot = Join-Path $workspaceRoot 'tmp-newbizintel-proofs'
}

$resolvedProofRoot = [System.IO.Path]::GetFullPath($ProofRoot)
$resolvedOutputRoot = [System.IO.Path]::GetFullPath($outputRoot)
$outputPrefix = $resolvedOutputRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (
    $resolvedProofRoot.Equals($resolvedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $resolvedProofRoot.StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw "NewBizIntel proof artifacts must not be written inside the delivery output root. Use a proof root outside '$resolvedOutputRoot'. Requested: $resolvedProofRoot"
}

if (-not $NoCreate) {
    New-Item -ItemType Directory -Path $resolvedProofRoot -Force | Out-Null
}

$resolvedProofRoot
