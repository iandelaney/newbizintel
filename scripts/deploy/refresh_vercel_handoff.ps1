param(
    [Parameter(Mandatory = $true)]
    [string]$BrandFolder,

    [string]$HandoffFolder
)

$ErrorActionPreference = 'Stop'

$resolvedBrandFolder = (Resolve-Path -LiteralPath $BrandFolder).Path
$archiveFolder = Join-Path $resolvedBrandFolder 'archive'

if (-not (Test-Path -LiteralPath $archiveFolder)) {
    throw "Archive folder not found: $archiveFolder"
}

$portableHtml = Join-Path $archiveFolder 'newbizintel-report-portable.html'
$pptx = Join-Path $archiveFolder 'newbizintel-report.pptx'
$reportData = Join-Path $resolvedBrandFolder 'report-data.json'

if (-not (Test-Path -LiteralPath $portableHtml)) {
    throw "Portable HTML not found: $portableHtml"
}

if (-not $HandoffFolder) {
    $HandoffFolder = $resolvedBrandFolder
}

$resolvedHandoffFolder = [System.IO.Path]::GetFullPath($HandoffFolder)
$brandRootWithSeparator = $resolvedBrandFolder.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (($resolvedHandoffFolder -ne $resolvedBrandFolder) -and (-not $resolvedHandoffFolder.StartsWith($brandRootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Handoff folder must be the brand output folder or a child of it. Brand folder: $resolvedBrandFolder. Requested handoff: $resolvedHandoffFolder"
}
New-Item -ItemType Directory -Force -Path $resolvedHandoffFolder | Out-Null

$indexHtml = Join-Path $resolvedHandoffFolder 'index.html'
$portableHtmlCopy = Join-Path $resolvedHandoffFolder 'newbizintel-report-portable.html'
$pptxCopy = Join-Path $resolvedHandoffFolder 'newbizintel-report.pptx'
$reportDataCopy = Join-Path $resolvedHandoffFolder 'report-data.json'
$sourceSlideAssets = Join-Path $resolvedBrandFolder 'slide-assets'
$handoffSlideAssets = Join-Path $resolvedHandoffFolder 'slide-assets'

if ($portableHtml -ine $indexHtml) {
    Copy-Item -LiteralPath $portableHtml -Destination $indexHtml -Force
}
if ($portableHtml -ine $portableHtmlCopy) {
    Copy-Item -LiteralPath $portableHtml -Destination $portableHtmlCopy -Force
}

if ((Test-Path -LiteralPath $pptx) -and ($pptx -ine $pptxCopy)) {
    Copy-Item -LiteralPath $pptx -Destination $pptxCopy -Force
}

if ((Test-Path -LiteralPath $reportData) -and ($reportData -ine $reportDataCopy)) {
    Copy-Item -LiteralPath $reportData -Destination $reportDataCopy -Force
}

if ((Test-Path -LiteralPath $sourceSlideAssets) -and ($sourceSlideAssets -ine $handoffSlideAssets)) {
    if (Test-Path -LiteralPath $handoffSlideAssets) {
        Remove-Item -LiteralPath $handoffSlideAssets -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceSlideAssets -Destination $handoffSlideAssets -Recurse -Force
}

[System.IO.Directory]::SetLastWriteTime($resolvedHandoffFolder, [DateTime]::Now)

[pscustomobject]@{
    brand_folder = $resolvedBrandFolder
    archive_folder = $archiveFolder
    handoff_folder = $resolvedHandoffFolder
    index_html = $indexHtml
    portable_html = $portableHtmlCopy
    pptx = $(if (Test-Path -LiteralPath $pptxCopy) { $pptxCopy } else { $null })
    report_data = $(if (Test-Path -LiteralPath $reportDataCopy) { $reportDataCopy } else { $null })
    slide_assets = $(if (Test-Path -LiteralPath $handoffSlideAssets) { $handoffSlideAssets } else { $null })
} | ConvertTo-Json -Compress
