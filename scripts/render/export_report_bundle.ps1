param(
    [Parameter(Mandatory = $true)]
    [string]$HtmlPath,

    [string]$DataPath,

    [string]$BaseName = 'newbizintel-report',

    [string]$ArchiveDir,

    [switch]$SkipAssetValidation
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $HtmlPath)) {
    throw "HTML report not found: $HtmlPath"
}

$htmlItem = Get-Item -LiteralPath $HtmlPath
$outputDir = $htmlItem.DirectoryName
$pptxPath = Join-Path $outputDir ($BaseName + '.pptx')

if (-not $ArchiveDir) {
    $ArchiveDir = Join-Path $outputDir 'archive'
}
$ArchiveDir = [System.IO.Path]::GetFullPath($ArchiveDir)

if (-not $DataPath) {
    $candidateDataPath = Join-Path $outputDir 'report-data.json'
    if (Test-Path -LiteralPath $candidateDataPath) {
        $DataPath = $candidateDataPath
    }
}

$assetValidation = $null
if ($DataPath -and -not $SkipAssetValidation) {
    $assetValidation = & (Join-Path $PSScriptRoot '..\assets\validate_brand_assets.ps1') -DataPath $DataPath | ConvertFrom-Json
    if (-not $assetValidation.ok) {
        $warningLines = @($assetValidation.warnings) | ForEach-Object { "- $_" }
        throw ((
            @(
                'Brand asset validation failed.'
                'NewBizIntel requires an accurate square brand mark before export.'
                ''
            ) + $warningLines
        ) -join [Environment]::NewLine)
    }
}

$python = & (Join-Path $PSScriptRoot '..\common\resolve_python.ps1')
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null

$archiveHtmlPath = Join-Path $ArchiveDir ($BaseName + '-portable.html')
$archivePptxPath = $(if ($DataPath) { Join-Path $ArchiveDir ([System.IO.Path]::GetFileName($pptxPath)) } else { $null })
$archiveWarnings = @()

$selfContainedArgs = @(
    (Join-Path $PSScriptRoot 'make_html_self_contained.py'),
    '--html', $htmlItem.FullName,
    '--output', $archiveHtmlPath
)
if ($DataPath) {
    $selfContainedArgs += @('--data', $DataPath)
}

if ($DataPath) {
    if (-not (Test-Path -LiteralPath $DataPath)) {
        throw "Report data not found: $DataPath"
    }
}

& $python @selfContainedArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Standalone HTML export failed with exit code $LASTEXITCODE."
}

if ($DataPath) {
    if ($nodeCommand) {
        & $nodeCommand.Source (Join-Path $PSScriptRoot 'report_data_to_pptx.js') --help >$null 2>$null
    }
    if ($nodeCommand -and $LASTEXITCODE -eq 0) {
        & $nodeCommand.Source (Join-Path $PSScriptRoot 'report_data_to_pptx.js') --data $DataPath --pptx $pptxPath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "PPTX export failed with exit code $LASTEXITCODE."
        }
    }
    else {
        $archiveWarnings += 'PPTX export skipped because the native PPTX runtime is unavailable.'
        $archivePptxPath = $null
    }
}

if ($archivePptxPath) {
    Copy-Item -LiteralPath $pptxPath -Destination $archivePptxPath -Force
}

[pscustomobject]@{
    html = $htmlItem.FullName
    pptx = $(if ($DataPath -and (Test-Path -LiteralPath $pptxPath)) { $pptxPath } else { $null })
    asset_validation = $assetValidation
    archive = [pscustomobject]@{
        directory = $ArchiveDir
        html = $archiveHtmlPath
        pptx = $archivePptxPath
        warnings = $archiveWarnings
    }
} | ConvertTo-Json -Depth 6 -Compress
