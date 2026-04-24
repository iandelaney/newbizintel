param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$HandoffFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state

if (-not $HandoffFolder) {
    $HandoffFolder = Join-Path (Split-Path -Parent $context.brand_folder) 'vercel'
}

$canonicalDataPath = Join-Path $context.brand_folder 'report-data.json'
if (-not ($context.data_path -ieq $canonicalDataPath)) {
    Copy-Item -LiteralPath $context.data_path -Destination $canonicalDataPath -Force
}

$state.status.deploy = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$handoff = & (Join-Path $PSScriptRoot 'refresh_vercel_handoff.ps1') -BrandFolder $context.brand_folder -HandoffFolder $HandoffFolder | ConvertFrom-Json

$state.status.deploy = 'passed'
$state.gates.gate_7_delivery = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state
$taskList = & (Join-Path $PSScriptRoot '..\qa\audit_task_list.ps1') -DataPath $context.data_path | ConvertFrom-Json

[pscustomobject]@{
    module = 'deploy'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    task_list = $taskList
    handoff = $handoff
} | ConvertTo-Json -Depth 8 -Compress
