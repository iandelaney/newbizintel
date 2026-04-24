param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [ValidateSet('bootstrap', 'live-summary')]
    [string]$ResearchMode = 'bootstrap',
    [string]$ResearchSummaryPath
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
$buildResearchSummary = Join-Path $PSScriptRoot 'build_research_summary.ps1'
$validateResearchSummary = Join-Path $PSScriptRoot 'validate_research_summary.ps1'
$writeJsonUtf8 = Join-Path $context.repo_root 'scripts\common\write_json_utf8.ps1'

$state.status.research = 'in_progress'
$state.gates.gate_2_competitors = 'in_progress'
$state.gates.gate_3_research = 'in_progress'
$state.gates.gate_3a_semrush = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$summaryPath = Join-Path $context.brand_folder 'research-summary.json'

if ($ResearchMode -eq 'bootstrap') {
    $summaryBuild = & $buildResearchSummary -DataPath $context.data_path -OutputPath $summaryPath | ConvertFrom-Json
}
else {
    if (-not $ResearchSummaryPath) {
        throw 'ResearchMode live-summary requires -ResearchSummaryPath.'
    }

    $resolvedResearchSummaryPath = (Resolve-Path -LiteralPath $ResearchSummaryPath).Path
    $validation = & $validateResearchSummary -Path $resolvedResearchSummaryPath | ConvertFrom-Json
    if (-not $validation.ok) {
        throw ("Research summary validation failed: {0}" -f (@($validation.errors) -join '; '))
    }

    $importedSummary = Get-Content -LiteralPath $resolvedResearchSummaryPath -Raw | ConvertFrom-Json
    & $writeJsonUtf8 -Path $summaryPath -InputObject $importedSummary

    $summaryBuild = [pscustomobject]@{
        data = $context.data_path
        summary = $summaryPath
        mode = $importedSummary.mode
        imported_from = $resolvedResearchSummaryPath
    }
}

$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json

$state.locked_sets.competitors = @($summary.locked_sets.competitors)
$state.locked_sets.influential_news = @($summary.locked_sets.influential_news)
$state.notes = @($state.notes | Where-Object {
    $_ -ne 'Research module currently runs in bootstrap-from-report-data mode.' -and
    $_ -ne 'Research module is using an imported live research summary.' -and
    $_ -ne 'SEMrush evidence is currently blocked in the imported live research summary.'
})

if ([string]$summary.mode -eq 'bootstrap-from-report-data') {
    $state.notes += 'Research module currently runs in bootstrap-from-report-data mode.'
}
else {
    $state.notes += 'Research module is using an imported live research summary.'
}

$gate3Statuses = @(
    [string]$summary.status.competitor_discovery,
    [string]$summary.status.recent_news,
    [string]$summary.status.reputation_public_web,
    [string]$summary.status.source_gathering
)

$state.status.research = $(if ($gate3Statuses -contains 'failed') {
    'failed'
}
elseif ($gate3Statuses -contains 'blocked') {
    'blocked'
}
elseif ($gate3Statuses -contains 'pending') {
    'pending'
}
else {
    'passed'
})

$state.gates.gate_2_competitors = $summary.status.competitor_discovery
$state.gates.gate_3_research = $state.status.research
$state.gates.gate_3a_semrush = $summary.status.semrush
if ([string]$summary.status.semrush -eq 'blocked') {
    $state.notes += 'SEMrush evidence is currently blocked in the imported live research summary.'
}

& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'research'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    research_summary = $summaryPath
    research_mode = $ResearchMode
    summary = $summaryBuild
} | ConvertTo-Json -Depth 8 -Compress
