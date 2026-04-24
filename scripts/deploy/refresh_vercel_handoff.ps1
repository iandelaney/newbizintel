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
    $HandoffFolder = Join-Path (Split-Path -Parent $resolvedBrandFolder) 'vercel'
}

$resolvedHandoffFolder = [System.IO.Path]::GetFullPath($HandoffFolder)
New-Item -ItemType Directory -Force -Path $resolvedHandoffFolder | Out-Null

$indexHtml = Join-Path $resolvedHandoffFolder 'index.html'
$portableHtmlCopy = Join-Path $resolvedHandoffFolder 'newbizintel-report-portable.html'
$pptxCopy = Join-Path $resolvedHandoffFolder 'newbizintel-report.pptx'
$reportDataCopy = Join-Path $resolvedHandoffFolder 'report-data.json'
$sourceSlideAssets = Join-Path $resolvedBrandFolder 'slide-assets'
$handoffSlideAssets = Join-Path $resolvedHandoffFolder 'slide-assets'

Copy-Item -LiteralPath $portableHtml -Destination $indexHtml -Force
Copy-Item -LiteralPath $portableHtml -Destination $portableHtmlCopy -Force

if (Test-Path -LiteralPath $pptx) {
    Copy-Item -LiteralPath $pptx -Destination $pptxCopy -Force
}

if (Test-Path -LiteralPath $reportData) {
    Copy-Item -LiteralPath $reportData -Destination $reportDataCopy -Force
}

if (Test-Path -LiteralPath $sourceSlideAssets) {
    if (Test-Path -LiteralPath $handoffSlideAssets) {
        Remove-Item -LiteralPath $handoffSlideAssets -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceSlideAssets -Destination $handoffSlideAssets -Recurse -Force
}

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
