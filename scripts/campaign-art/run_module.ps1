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
$resolvePython = Join-Path $PSScriptRoot '..\common\resolve_python.ps1'

$state.status.campaign_art = 'in_progress'
$state.gates.gate_5b_campaign_art = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$python = & $resolvePython
$generation = & $python (Join-Path $PSScriptRoot 'generate_campaign_illustrations.py') --data $context.data_path | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
    throw "Campaign-art generation failed with exit code $LASTEXITCODE."
}

$importResult = $null
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

    $importResult = & $python @importArgs | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Campaign-art import failed with exit code $LASTEXITCODE."
    }

    $generation = & $python (Join-Path $PSScriptRoot 'generate_campaign_illustrations.py') --data $context.data_path | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Campaign-art refresh after import failed with exit code $LASTEXITCODE."
    }
}

$pendingFinalRaster = 0
if ($null -ne $generation.pending_final_raster) {
    $pendingFinalRaster = [int]$generation.pending_final_raster
}

if ($pendingFinalRaster -gt 0) {
    $state.status.campaign_art = 'blocked'
    $state.gates.gate_5b_campaign_art = 'blocked'
}
else {
    $state.status.campaign_art = 'passed'
    $state.gates.gate_5b_campaign_art = 'passed'
}
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
} | ConvertTo-Json -Depth 8 -Compress
