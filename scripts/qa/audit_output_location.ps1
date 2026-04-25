param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$resolveOutputRoot = Join-Path $repoRoot 'scripts\common\resolve_output_root.ps1'
$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$outputRoot = & $resolveOutputRoot -RepoRoot $repoRoot
$resolvedOutputRoot = [System.IO.Path]::GetFullPath($outputRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
$outputRootWithSeparator = $resolvedOutputRoot + [System.IO.Path]::DirectorySeparatorChar

$errors = New-Object System.Collections.Generic.List[string]
if (-not $brandFolder.StartsWith($outputRootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
    $errors.Add("Brand output folder must be inside the resolved output root. Output root: $resolvedOutputRoot. Brand folder: $brandFolder")
}

$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$brandSlug = [string]$data.brand.slug
if ([string]::IsNullOrWhiteSpace($brandSlug)) {
    $errors.Add('Brand slug is missing from report-data.json, so the canonical output folder cannot be verified.')
}
else {
    $canonicalBrandFolder = [System.IO.Path]::GetFullPath((Join-Path $resolvedOutputRoot $brandSlug)).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $resolvedBrandFolder = [System.IO.Path]::GetFullPath($brandFolder).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    if (-not $resolvedBrandFolder.Equals($canonicalBrandFolder, [System.StringComparison]::OrdinalIgnoreCase)) {
        $errors.Add("Brand output folder must be exactly the canonical output folder. Expected: $canonicalBrandFolder. Actual: $resolvedBrandFolder")
    }
}

foreach ($required in @('newbizintel-report.html', 'newbizintel-report.pptx', 'report-data.json', 'run-state.json')) {
    $path = Join-Path $brandFolder $required
    if (-not (Test-Path -LiteralPath $path)) {
        $errors.Add("Required output file is missing from brand output folder: $path")
    }
}

if ($errors.Count -gt 0) {
    throw ("Output location audit failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    output_root = $resolvedOutputRoot
    brand_folder = $brandFolder
    canonical_brand_folder = $(if ($brandSlug) { Join-Path $resolvedOutputRoot $brandSlug } else { $null })
    data = $resolvedDataPath
} | ConvertTo-Json -Depth 4 -Compress
