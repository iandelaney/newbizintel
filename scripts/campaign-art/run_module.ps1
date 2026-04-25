param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$ImportSourceDir,
    [switch]$ImportLatestGeneratedBatch,
    [switch]$OverwriteFinalArt
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')
$resolvePython = Join-Path $PSScriptRoot '..\common\resolve_python.ps1'

trap {
    if ($null -ne $state -and $null -ne $context) {
        $state.status.campaign_art = 'failed'
        $state.gates.gate_5b_campaign_art = 'failed'
        & $context.save_run_state -Path $context.run_state_path -State $state
    }
    throw
}

$state.status.campaign_art = 'in_progress'
$state.gates.gate_5b_campaign_art = 'in_progress'
Add-NewBizHybridEvent -State $state -Type fanout -Key 'campaign_art.prep' -Jobs @(
    'campaign-art-prompt-manifest',
    'campaign-art-brief',
    'final-raster-import-check'
) -Notes @('Campaign art prep fans out into prompt/brief assets, but final promotion remains deterministic and audited.')
& $context.save_run_state -Path $context.run_state_path -State $state

$python = & $resolvePython
$generation = & $python (Join-Path $PSScriptRoot 'generate_campaign_illustrations.py') --data $context.data_path --manifest-only | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
    throw "Campaign-art generation failed with exit code $LASTEXITCODE."
}

$campaignPatchManifest = [string]$generation.report_data_patch_manifest
if ([string]::IsNullOrWhiteSpace($campaignPatchManifest) -or -not (Test-Path -LiteralPath $campaignPatchManifest)) {
    throw 'Campaign-art generation did not produce a report-data patch manifest.'
}
$campaignReduction = & (Join-Path $PSScriptRoot '..\common\apply_report_data_manifest.ps1') -DataPath $context.data_path -ManifestPath $campaignPatchManifest -Domain 'campaign-art' | ConvertFrom-Json
if ($campaignReduction.ok -ne $true) {
    throw 'Campaign-art report-data reducer failed.'
}

$importResult = $null
$importReduction = $null
if ($ImportSourceDir -or $ImportLatestGeneratedBatch) {
    $importArgs = @(
        (Join-Path $PSScriptRoot 'import_final_campaign_art.py'),
        '--data', $context.data_path
    )
    if ($ImportSourceDir) {
        $importArgs += @('--source-dir', $ImportSourceDir)
    }
    if ($ImportLatestGeneratedBatch) {
        $importArgs += '--latest-generated-batch'
    }
    if ($OverwriteFinalArt) {
        $importArgs += '--overwrite-final'
    }
    $importArgs += '--manifest-only'

    $importResult = & $python @importArgs | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Campaign-art import failed with exit code $LASTEXITCODE."
    }

    $importPatchManifest = [string]$importResult.report_data_patch_manifest
    if ([string]::IsNullOrWhiteSpace($importPatchManifest) -or -not (Test-Path -LiteralPath $importPatchManifest)) {
        throw 'Campaign-art import did not produce a report-data patch manifest.'
    }
    $importReduction = & (Join-Path $PSScriptRoot '..\common\apply_report_data_manifest.ps1') -DataPath $context.data_path -ManifestPath $importPatchManifest -Domain 'campaign-art' | ConvertFrom-Json
    if ($importReduction.ok -ne $true) {
        throw 'Campaign-art import report-data reducer failed.'
    }

    $generation = & $python (Join-Path $PSScriptRoot 'generate_campaign_illustrations.py') --data $context.data_path --manifest-only | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Campaign-art refresh after import failed with exit code $LASTEXITCODE."
    }

    $campaignPatchManifest = [string]$generation.report_data_patch_manifest
    if ([string]::IsNullOrWhiteSpace($campaignPatchManifest) -or -not (Test-Path -LiteralPath $campaignPatchManifest)) {
        throw 'Campaign-art refresh did not produce a report-data patch manifest.'
    }
    $campaignReduction = & (Join-Path $PSScriptRoot '..\common\apply_report_data_manifest.ps1') -DataPath $context.data_path -ManifestPath $campaignPatchManifest -Domain 'campaign-art' | ConvertFrom-Json
    if ($campaignReduction.ok -ne $true) {
        throw 'Campaign-art report-data reducer failed after import.'
    }
}

$pendingFinalRaster = 0
if ($null -ne $generation.pending_final_raster) {
    $pendingFinalRaster = [int]$generation.pending_final_raster
}

$contractAudit = $null
if ($pendingFinalRaster -gt 0) {
    $state.status.campaign_art = 'blocked'
    $state.gates.gate_5b_campaign_art = 'blocked'
}
else {
    try {
        $contractAudit = & (Join-Path $PSScriptRoot '..\qa\audit_campaign_art_contract.ps1') -DataPath $context.data_path | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $contractAudit.ok -ne $true) {
            throw 'Campaign-art contract audit returned ok:false after generation/import.'
        }
    }
    catch {
        $state.status.campaign_art = 'failed'
        $state.gates.gate_5b_campaign_art = 'failed'
        & $context.save_run_state -Path $context.run_state_path -State $state
        throw
    }

    $state.status.campaign_art = 'passed'
    $state.gates.gate_5b_campaign_art = 'passed'
}
Add-NewBizHybridEvent -State $state -Type reducer -Key 'campaign_art.asset_manifest_reducer' -Outputs @(
    $(if ($null -ne $generation.prompt_manifest) { [string]$generation.prompt_manifest } else { 'campaign-art-prompt-manifest' }),
    $(if ($null -ne $generation.prompt_brief) { [string]$generation.prompt_brief } else { 'campaign-art-brief' }),
    $(if ($null -ne $generation.report_data_patch_manifest) { [string]$generation.report_data_patch_manifest } else { 'campaign-art-report-data-patch' })
) -Notes @(
    "pending_final_raster:$pendingFinalRaster",
    'canonical_writer:apply_report_data_manifest',
    ('new_sha256:{0}' -f [string]$campaignReduction.new_sha256)
)
& $context.save_run_state -Path $context.run_state_path -State $state

$dataJson = Get-Content -Path $context.data_path -Raw | ConvertFrom-Json
$creativeSection = $dataJson.creative_campaign_ideas
if ($null -eq $creativeSection) {
    $creativeSection = $dataJson.creative_campaigns
}

[pscustomobject]@{
    module = 'campaign-art'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    prompt_manifest = $(if ($null -ne $creativeSection) { $creativeSection.illustration_prompt_manifest } else { $null })
    prompt_brief = $(if ($null -ne $creativeSection) { $creativeSection.illustration_prompt_brief } else { $null })
    generation = $generation
    import = $importResult
    import_reduction = $importReduction
    campaign_reduction = $campaignReduction
    contract_audit = $contractAudit
} | ConvertTo-Json -Depth 8 -Compress
