param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
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

[pscustomobject]@{
    module = 'campaign-art'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    generation = $generation
} | ConvertTo-Json -Depth 8 -Compress
