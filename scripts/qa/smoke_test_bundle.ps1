param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$TemplatePath
)

$ErrorActionPreference = 'Stop'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$results = [ordered]@{}

$results.schema_validation = & (Join-Path $PSScriptRoot '..\structure\validate_report_data.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
$results.asset_validation = & (Join-Path $PSScriptRoot '..\assets\validate_brand_assets.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json

$renderParams = @{ DataPath = $resolvedDataPath }
if ($TemplatePath) {
    $renderParams.TemplatePath = $TemplatePath
}

$renderResult = & (Join-Path $PSScriptRoot '..\render\render_report.ps1') @renderParams | ConvertFrom-Json
$html = Get-Content -LiteralPath $renderResult.html -Raw
if ($html -match '(?i)file:///') {
    throw 'Rendered HTML still contains local file URIs.'
}

$results.render = $renderResult
$results.presentation = & (Join-Path $PSScriptRoot 'audit_presentation_layer.ps1') -HtmlPath $renderResult.html -DataPath $resolvedDataPath | ConvertFrom-Json

$exportResult = & (Join-Path $PSScriptRoot '..\render\export_report_bundle.ps1') -HtmlPath $renderResult.html -DataPath $resolvedDataPath | ConvertFrom-Json
$portableHtml = Get-Content -LiteralPath $exportResult.archive.html -Raw
if ($portableHtml -match '(?i)file:///') {
    throw 'Portable archive HTML still contains local file URIs.'
}
if ($portableHtml -match '(?i)<img\b[^>]*\bsrc="https?://') {
    throw 'Portable archive HTML still contains external image references.'
}

$results.export = $exportResult

$bundleResult = & (Join-Path $PSScriptRoot '..\render\build_report_bundle.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
$results.bundle = $bundleResult

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    schema_validation = $results.schema_validation
    asset_validation = $results.asset_validation
    render_html = $results.render.html
    presentation = $results.presentation
    archive_html = $results.export.archive.html
    pptx = $results.export.pptx
    bundle = $results.bundle
} | ConvertTo-Json -Depth 8 -Compress
