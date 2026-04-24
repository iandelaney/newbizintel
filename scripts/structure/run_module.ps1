param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$ResearchSummaryPath
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
. (Join-Path $PSScriptRoot '..\common\state_freshness.ps1')
$state = $context.state
$mergeResearchSummary = Join-Path $PSScriptRoot 'merge_research_summary.ps1'

$state.status.structure = 'in_progress'
$state.gates.gate_4_report_data = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$merge = & $mergeResearchSummary -DataPath $context.data_path -ResearchSummaryPath $ResearchSummaryPath | ConvertFrom-Json
$validation = & (Join-Path $PSScriptRoot 'validate_report_data.ps1') -DataPath $context.data_path | ConvertFrom-Json
Update-ReportDataFreshness -State $state -DataPath $context.data_path

$state.status.structure = 'passed'
$state.gates.gate_4_report_data = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'structure'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    merge = $merge
    validation = $validation
} | ConvertTo-Json -Depth 8 -Compress
