param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state

$state.status.qa = 'in_progress'
$state.gates.gate_6_render_outputs = 'in_progress'
$state.gates.gate_6a_editorial_quality = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$qa = & (Join-Path $PSScriptRoot 'smoke_test_bundle.ps1') -DataPath $context.data_path | ConvertFrom-Json
$editorial = & (Join-Path $PSScriptRoot 'audit_editorial_quality.ps1') -DataPath $context.data_path | ConvertFrom-Json
$campaignArt = & (Join-Path $PSScriptRoot 'audit_campaign_art_contract.ps1') -DataPath $context.data_path | ConvertFrom-Json
$pptx = & (Join-Path $PSScriptRoot 'audit_pptx_output.ps1') -PptxPath $qa.pptx | ConvertFrom-Json

$state.status.qa = 'passed'
$state.gates.gate_6_render_outputs = 'passed'
$state.gates.gate_6a_editorial_quality = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'qa'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    qa = $qa
    editorial = $editorial
    campaign_art_contract = $campaignArt
    pptx = $pptx
} | ConvertTo-Json -Depth 8 -Compress
