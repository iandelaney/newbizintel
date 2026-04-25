param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$TemplatePath,

    [string]$BaseName = 'newbizintel-report'
)

$ErrorActionPreference = 'Stop'

$schemaValidation = & (Join-Path $PSScriptRoot '..\structure\validate_report_data.ps1') -DataPath $DataPath | ConvertFrom-Json

$renderParams = @{
    DataPath = $DataPath
}

if ($TemplatePath) {
    $renderParams.TemplatePath = $TemplatePath
}

$assetValidation = & (Join-Path $PSScriptRoot '..\assets\validate_brand_assets.ps1') -DataPath $DataPath | ConvertFrom-Json
$deliveryAssetValidation = & (Join-Path $PSScriptRoot '..\assets\validate_delivery_assets.ps1') -DataPath $DataPath | ConvertFrom-Json
$renderParams.SkipValidation = $true
$renderResult = & (Join-Path $PSScriptRoot 'render_report.ps1') @renderParams | ConvertFrom-Json
$exportResult = & (Join-Path $PSScriptRoot 'export_report_bundle.ps1') -HtmlPath $renderResult.html -DataPath $DataPath -BaseName $BaseName -SkipAssetValidation | ConvertFrom-Json

[pscustomobject]@{
    data = $renderResult.data
    template = $renderResult.template
    html = $renderResult.html
    pptx = $exportResult.pptx
    schema_validation = $schemaValidation
    asset_validation = $assetValidation
    delivery_asset_validation = $deliveryAssetValidation
    archive = $exportResult.archive
} | ConvertTo-Json -Depth 6 -Compress
