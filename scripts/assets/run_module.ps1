param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state

$state.status.assets = 'in_progress'
$state.gates.gate_5_assets = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$validation = & (Join-Path $PSScriptRoot 'validate_brand_assets.ps1') -DataPath $context.data_path | ConvertFrom-Json

$state.status.assets = 'passed'
$state.gates.gate_5_assets = 'passed'
$state.gates.gate_5a_source_badges = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'assets'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    validation = $validation
} | ConvertTo-Json -Depth 8 -Compress
