param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$HandoffFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\assertions.ps1')

trap {
    if ($null -ne $state -and $null -ne $context) {
        $state.status.deploy = 'failed'
        $state.gates.gate_7_delivery = 'failed'
        $state.gates.gate_10_delivery_handoff = 'failed'
        & $context.save_run_state -Path $context.run_state_path -State $state
    }
    throw
}

if (-not $HandoffFolder) {
    $HandoffFolder = $context.brand_folder
}

$canonicalDataPath = Join-Path $context.brand_folder 'report-data.json'
if (-not ($context.data_path -ieq $canonicalDataPath)) {
    Copy-Item -LiteralPath $context.data_path -Destination $canonicalDataPath -Force
}

$state.status.deploy = 'in_progress'
$state.gates.gate_7_delivery = 'in_progress'
$state.gates.gate_10_delivery_handoff = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$handoff = & (Join-Path $PSScriptRoot 'refresh_vercel_handoff.ps1') -BrandFolder $context.brand_folder -HandoffFolder $HandoffFolder | ConvertFrom-Json

Assert-NewBizPath -Name 'Handoff index HTML' -Path $handoff.index_html
Assert-NewBizPath -Name 'Handoff portable HTML' -Path $handoff.portable_html
Assert-NewBizPath -Name 'Handoff report data' -Path $handoff.report_data
Assert-NewBizPath -Name 'Handoff PPTX' -Path $handoff.pptx
Assert-NewBizPath -Name 'Handoff slide assets' -Path $handoff.slide_assets

$state.status.deploy = 'passed'
$state.gates.gate_7_delivery = 'passed'
$state.gates.gate_10_delivery_handoff = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

try {
    $taskList = & (Join-Path $PSScriptRoot '..\qa\audit_task_list.ps1') -DataPath $context.data_path | ConvertFrom-Json
    Assert-NewBizOkResult -Name 'Task-list audit after deploy pass' -Result $taskList
}
catch {
    $state.status.deploy = 'failed'
    $state.gates.gate_7_delivery = 'failed'
    $state.gates.gate_10_delivery_handoff = 'failed'
    & $context.save_run_state -Path $context.run_state_path -State $state
    throw
}

[pscustomobject]@{
    module = 'deploy'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    task_list = $taskList
    handoff = $handoff
} | ConvertTo-Json -Depth 8 -Compress
