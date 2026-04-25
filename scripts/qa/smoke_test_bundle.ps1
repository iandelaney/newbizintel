param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$TemplatePath,

    [switch]$NoParallel
)

$ErrorActionPreference = 'Stop'

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$results = [ordered]@{}
. (Join-Path $PSScriptRoot '..\common\invoke_json_jobs.ps1')
. (Join-Path $PSScriptRoot '..\common\assertions.ps1')

$initialAuditJobs = @(
    @{
        key = 'intake_identity'
        path = Join-Path $PSScriptRoot 'audit_intake_identity.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'schema_validation'
        path = Join-Path $PSScriptRoot '..\structure\validate_report_data.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'asset_validation'
        path = Join-Path $PSScriptRoot '..\assets\validate_brand_assets.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'delivery_assets'
        path = Join-Path $PSScriptRoot '..\assets\validate_delivery_assets.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'required_logos'
        path = Join-Path $PSScriptRoot '..\assets\build_required_logo_manifest.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'source_badges'
        path = Join-Path $PSScriptRoot '..\assets\build_source_badge_manifest.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'editorial'
        path = Join-Path $PSScriptRoot 'audit_editorial_quality.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    },
    @{
        key = 'campaign_art_contract'
        path = Join-Path $PSScriptRoot 'audit_campaign_art_contract.ps1'
        parameters = @{ DataPath = $resolvedDataPath }
    }
)

$initialAudits = Invoke-JsonJobs -Jobs $initialAuditJobs -WorkingDirectory (Split-Path -Parent $resolvedDataPath) -Sequential:$NoParallel
$results.intake_identity = $initialAudits.intake_identity
$results.schema_validation = $initialAudits.schema_validation
$results.asset_validation = $initialAudits.asset_validation
$results.delivery_assets = $initialAudits.delivery_assets
$results.required_logos = $initialAudits.required_logos
$results.source_badges = $initialAudits.source_badges
$results.editorial = $initialAudits.editorial
$results.campaign_art_contract = $initialAudits.campaign_art_contract

Assert-NewBizOkResult -Name 'Intake identity audit' -Result $results.intake_identity
Assert-NewBizOkResult -Name 'Schema validation' -Result $results.schema_validation
Assert-NewBizOkResult -Name 'Brand asset validation' -Result $results.asset_validation
Assert-NewBizOkResult -Name 'Delivery asset validation' -Result $results.delivery_assets
Assert-NewBizOkResult -Name 'Required logo manifest' -Result $results.required_logos
Assert-NewBizOkResult -Name 'Source badge manifest' -Result $results.source_badges
Assert-NewBizOkResult -Name 'Editorial audit' -Result $results.editorial
Assert-NewBizOkResult -Name 'Campaign art contract audit' -Result $results.campaign_art_contract

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
if ($results.presentation.ok -ne $true) {
    throw ("Presentation audit failed: {0}" -f (@($results.presentation.errors) -join '; '))
}

$exportResult = & (Join-Path $PSScriptRoot '..\render\export_report_bundle.ps1') -HtmlPath $renderResult.html -DataPath $resolvedDataPath | ConvertFrom-Json
$portableHtml = Get-Content -LiteralPath $exportResult.archive.html -Raw
if ($portableHtml -match '(?i)file:///') {
    throw 'Portable archive HTML still contains local file URIs.'
}
if ($portableHtml -match '(?i)<img\b[^>]*\bsrc="https?://') {
    throw 'Portable archive HTML still contains external image references.'
}

$results.export = $exportResult
$results.pptx = & (Join-Path $PSScriptRoot 'audit_pptx_output.ps1') -PptxPath $exportResult.pptx | ConvertFrom-Json
Assert-NewBizOkResult -Name 'PPTX audit' -Result $results.pptx

$results.bundle = [pscustomobject]@{
    data = $resolvedDataPath
    template = $results.render.template
    html = $results.render.html
    pptx = $results.export.pptx
    schema_validation = $results.schema_validation
    asset_validation = $results.asset_validation
    archive = $results.export.archive
    reused_current_export = $true
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    intake_identity = $results.intake_identity
    schema_validation = $results.schema_validation
    asset_validation = $results.asset_validation
    required_logos = $results.required_logos
    source_badges = $results.source_badges
    editorial = $results.editorial
    campaign_art_contract = $results.campaign_art_contract
    render_html = $results.render.html
    presentation = $results.presentation
    archive_html = $results.export.archive.html
    pptx = $results.export.pptx
    pptx_audit = $results.pptx
    bundle = $results.bundle
} | ConvertTo-Json -Depth 8 -Compress
