param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$Website
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder -Website $Website
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')
Ensure-NewBizHybridExecution -State $state

$data = Get-Content -LiteralPath $context.data_path -Raw | ConvertFrom-Json
$websiteValue = [string]$data.brand.website
if ([string]::IsNullOrWhiteSpace($websiteValue) -or $websiteValue -match '^https?://example\.com/?$') {
    $state.status.intake = 'failed'
    $state.gates.gate_1_intake = 'failed'
    & $context.save_run_state -Path $context.run_state_path -State $state
    throw 'Intake failed: brand.website must be a confirmed real website, not example.com.'
}

$state.status.intake = 'passed'
$state.gates.gate_1_intake = 'passed'

& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'intake'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    website = $websiteValue
} | ConvertTo-Json -Depth 8 -Compress
