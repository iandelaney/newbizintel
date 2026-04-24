param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state

$state.status.intake = 'passed'
$state.gates.gate_1_intake = 'passed'

& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'intake'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
} | ConvertTo-Json -Depth 8 -Compress
