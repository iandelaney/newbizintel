param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [ValidateSet('bootstrap', 'live-summary', 'workpacks')]
    [string]$ResearchMode = 'bootstrap',
    [string]$ResearchSummaryPath,
    [string[]]$SearchWorkpacks = @(),
    [switch]$AllowResearchEscalation,
    [bool]$ComposioSemrushAvailable = $false,
    [bool]$JinaFallbackAvailable = $true,
    [string]$SemrushApiKey,
    [switch]$UseSemrushApi,
    [ValidateSet('uk', 'us')]
    [string]$SemrushDatabase = 'uk'
)

$ErrorActionPreference = 'Stop'

if (-not [string]::IsNullOrWhiteSpace($SemrushApiKey)) {
    $env:SEMRUSH_API_KEY = $SemrushApiKey
}

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
. (Join-Path $PSScriptRoot '..\common\state_freshness.ps1')
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')
$state = $context.state
$buildResearchSummary = Join-Path $PSScriptRoot 'build_research_summary.ps1'
$validateResearchSummary = Join-Path $PSScriptRoot 'validate_research_summary.ps1'
$auditResearchWorkpacks = Join-Path $PSScriptRoot 'audit_research_workpacks.ps1'
$reduceSearchWorkpacks = Join-Path $PSScriptRoot 'reduce_search_workpacks.py'
$probeSemrushAccess = Join-Path $PSScriptRoot 'probe_semrush_access.ps1'
$prepareSemrushRequests = Join-Path $PSScriptRoot 'prepare_semrush_requests.ps1'
$resolvePython = Join-Path $context.repo_root 'scripts\common\resolve_python.ps1'
$writeJsonUtf8 = Join-Path $context.repo_root 'scripts\common\write_json_utf8.ps1'

$state.status.research = 'in_progress'
$state.gates.gate_2_competitors = 'in_progress'
$state.gates.gate_3_research = 'in_progress'
$state.gates.gate_3a_semrush = 'in_progress'
Add-NewBizHybridEvent -State $state -Type fanout -Key 'research.evidence_collection' -Jobs @(
    "research_mode:$ResearchMode",
    "summary_builder:$([System.IO.Path]::GetFileName($buildResearchSummary))",
    "search_workpacks:$(@($SearchWorkpacks).Count)",
    "codex_synthesis:$($ResearchMode -eq 'workpacks')",
    "composio_semrush_available:$ComposioSemrushAvailable",
    "jina_fallback_available:$JinaFallbackAvailable",
    "semrush_api:$($UseSemrushApi.IsPresent)"
) -Notes @('Research collectors must write isolated evidence or summary files before the reducer updates canonical state.')
& $context.save_run_state -Path $context.run_state_path -State $state

$summaryPath = Join-Path $context.brand_folder 'research-summary.json'
$semrushApiResult = $null
$semrushAccessPath = Join-Path $context.brand_folder 'semrush-access.json'
$semrushRequestPlanPath = Join-Path $context.brand_folder 'semrush-composio-request-plan.json'

if ($ResearchMode -eq 'bootstrap') {
    $summaryBuild = & $buildResearchSummary -DataPath $context.data_path -OutputPath $summaryPath | ConvertFrom-Json
}
elseif ($ResearchMode -eq 'workpacks') {
    if (@($SearchWorkpacks).Count -eq 0) {
        throw 'ResearchMode workpacks requires at least one -SearchWorkpacks path.'
    }

    $auditParams = @{
        BrandFolder = $context.brand_folder
        SearchWorkpacks = $SearchWorkpacks
    }
    if ($AllowResearchEscalation) {
        $auditParams.AllowResearchEscalation = $true
    }
    $workpackAudit = & $auditResearchWorkpacks @auditParams | ConvertFrom-Json
    if (-not $workpackAudit.ok) {
        throw ("Research workpack audit failed: {0}" -f (@($workpackAudit.errors) -join '; '))
    }
    if (-not $workpackAudit.cheap_search_sufficient -and -not $AllowResearchEscalation) {
        throw 'Cheap search workpacks are insufficient for trusted synthesis. Add targeted search/Jina/direct-source workpacks or explicitly allow research escalation.'
    }

    $python = & $resolvePython
    $pythonArgs = @(
        $reduceSearchWorkpacks,
        '--data', $context.data_path,
        '--output', $summaryPath
    )
    foreach ($workpack in @($SearchWorkpacks)) {
        $pythonArgs += @('--workpack', $workpack)
    }

    $reduceResult = & $python @pythonArgs | ConvertFrom-Json
    $validation = & $validateResearchSummary -Path $summaryPath | ConvertFrom-Json
    if (-not $validation.ok) {
        throw ("Reduced research summary validation failed: {0}" -f (@($validation.errors) -join '; '))
    }

    $summaryBuild = [pscustomobject]@{
        data = $context.data_path
        summary = $summaryPath
        mode = 'live-search-workpack-summary'
        workpack_audit = $workpackAudit
        reduced = $reduceResult
        synthesis_owner = 'codex'
        tavily_research_used = $false
    }
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

$semrushProbeParams = @{
    DataPath = $context.data_path
    BrandFolder = $context.brand_folder
    OutputPath = $semrushAccessPath
    Database = $SemrushDatabase
}
if ($ComposioSemrushAvailable) {
    $semrushProbeParams.ComposioMcpAvailable = $true
}
if ($JinaFallbackAvailable) {
    $semrushProbeParams.JinaFallbackAvailable = $true
}
$semrushRequestPlan = & $prepareSemrushRequests -DataPath $context.data_path -Database $SemrushDatabase | ConvertFrom-Json
& $writeJsonUtf8 -Path $semrushRequestPlanPath -InputObject $semrushRequestPlan
$semrushAccessResult = & $probeSemrushAccess @semrushProbeParams | ConvertFrom-Json
$shouldUseSemrushApi = $UseSemrushApi.IsPresent -or ([string]$semrushAccessResult.selected_provider -eq 'direct-api')

if ($shouldUseSemrushApi) {
    $semrushOutputPath = Join-Path $context.brand_folder 'semrush-api-evidence.json'
    $semrushJson = & (Join-Path $PSScriptRoot 'collect_semrush_api.ps1') -DataPath $context.data_path -Database $SemrushDatabase -OutputPath $semrushOutputPath
    $semrushApiResult = $semrushJson | ConvertFrom-Json
    if ([string]$semrushApiResult.status -in @('passed', 'partial')) {
        & (Join-Path $PSScriptRoot 'apply_semrush_api_evidence.ps1') -ResearchSummaryPath $summaryPath -SemrushEvidencePath $semrushOutputPath | Out-Null
    }
}

Add-NewBizHybridEvent -State $state -Type reducer -Key 'research.summary_reducer' -Outputs @($summaryPath) -Notes @('Research evidence reduced into research-summary.json before structure updates report-data.json.')

$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if (Test-Path -LiteralPath $semrushAccessPath) {
    $semrushAccess = Get-Content -LiteralPath $semrushAccessPath -Raw | ConvertFrom-Json
    $standardSemrushBackupPaths = @(
        (Join-Path $context.brand_folder 'semrush-evidence.json'),
        (Join-Path $context.brand_folder 'semrush-plugin-evidence.json'),
        (Join-Path $context.brand_folder 'semrush-composio-evidence.json'),
        (Join-Path $context.brand_folder 'research-workpacks\98-semrush-plugin.json'),
        (Join-Path $context.brand_folder 'research-workpacks\98-semrush-composio.json')
    )
    $semrushBackupPath = $standardSemrushBackupPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $semrushBackup = $null
    if ($semrushBackupPath) {
        $semrushBackup = Get-Content -LiteralPath $semrushBackupPath -Raw | ConvertFrom-Json
    }
    if ($null -ne $semrushApiResult) {
        $semrushAccess.evidence_status = [string]$semrushApiResult.status
        & $writeJsonUtf8 -Path $semrushAccessPath -InputObject $semrushAccess
    }

    if ($null -eq $summary.PSObject.Properties['semrush_access']) {
        $summary | Add-Member -NotePropertyName 'semrush_access' -NotePropertyValue $semrushAccess
    }
    else {
        $summary.semrush_access = $semrushAccess
    }

    if ([string]$summary.status.semrush -eq 'passed' -and [string]$semrushAccess.selected_provider -notin @('direct-api', 'composio-mcp') -and $null -eq $semrushApiResult) {
        $summary.status.semrush = 'quota-limited'
        $summary.notes = @(@($summary.notes) + 'Existing SEO evidence was retained, but this run did not verify SEMrush through direct API or Composio MCP; treat SEMrush as quota-limited/fallback-backed.')
    }
    elseif ($null -ne $semrushApiResult -and [string]$semrushApiResult.status -notin @('passed', 'partial')) {
        if ([bool]$semrushAccess.composio_mcp.available) {
            if ($semrushBackup -and [string]$semrushBackup.status -in @('passed', 'partial')) {
                if (@($semrushBackup.seo.semrush_evidence).Count -gt 0) {
                    $summary.seo.semrush_evidence = @($semrushBackup.seo.semrush_evidence)
                }
                if (@($semrushBackup.seo.priority_issues).Count -gt 0) {
                    $summary.seo.priority_issues = @($semrushBackup.seo.priority_issues)
                }
                $summary.status.semrush = [string]$semrushBackup.status
                $summary.semrush_backup = [pscustomobject]@{
                    provider = 'composio-semrush'
                    status = [string]$semrushBackup.status
                    path = $semrushBackupPath
                }
                $summary.notes = @(@($summary.notes) + "Composio SEMrush backup evidence was auto-merged from $([System.IO.Path]::GetFileName($semrushBackupPath)).")
                $semrushAccess.selected_provider = 'composio-mcp'
                $semrushAccess.evidence_status = [string]$semrushBackup.status
            }
            else {
                $summary.status.semrush = 'quota-limited'
                $summary.semrush_backup = [pscustomobject]@{
                    provider = 'composio-semrush'
                    status = 'awaiting-evidence-file'
                    request_plan_path = $semrushRequestPlanPath
                    accepted_paths = @($standardSemrushBackupPaths)
                }
                $summary.notes = @(@($summary.notes) + 'Direct SEMrush API was selected but did not return usable evidence; Composio SEMrush request plan was written automatically and the runner will merge a standard backup evidence file when present.')
                $semrushAccess.selected_provider = 'composio-mcp'
                $semrushAccess.evidence_status = 'pending'
            }
        }
        else {
            $summary.status.semrush = $(if ([string]$semrushApiResult.status) { [string]$semrushApiResult.status } else { 'blocked' })
            $summary.notes = @(@($summary.notes) + 'Direct SEMrush API was selected but did not return usable evidence, and no Composio SEMrush backup was available; do not mark SEMrush evidence as passed for this run.')
        }
    }

    $summary.semrush_access = $semrushAccess
    & $writeJsonUtf8 -Path $summaryPath -InputObject $summary
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    & $writeJsonUtf8 -Path $semrushAccessPath -InputObject $semrushAccess
}
Update-ResearchSummaryFreshness -State $state -SummaryPath $summaryPath

$state.locked_sets.competitors = @($summary.locked_sets.competitors)
$state.locked_sets.influential_news = @($summary.locked_sets.influential_news)
$state.notes = @($state.notes | Where-Object {
    $_ -ne 'Research module currently runs in bootstrap-from-report-data mode.' -and
    $_ -ne 'Research module is using an imported live research summary.' -and
    $_ -ne 'SEMrush evidence is currently blocked in the imported live research summary.' -and
    $_ -ne 'SEMrush evidence is quota-limited; keep the Composio request plan with the workpack and use Jina/public web as backup evidence.'
})

if ([string]$summary.mode -eq 'bootstrap-from-report-data') {
    $state.notes += 'Research module currently runs in bootstrap-from-report-data mode.'
}
elseif ([string]$summary.mode -eq 'live-search-workpack-summary') {
    $state.notes += 'Research module reduced cheap search workpacks; Codex owns synthesis and Tavily Research was not used.'
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
elseif ([string]$summary.status.semrush -eq 'quota-limited') {
    $state.notes += 'SEMrush evidence is quota-limited; keep the Composio request plan with the workpack and use Jina/public web as backup evidence.'
}

& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'research'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    research_summary = $summaryPath
    research_mode = $ResearchMode
    semrush_api = $semrushApiResult
    semrush_access = $semrushAccessResult
    summary = $summaryBuild
} | ConvertTo-Json -Depth 8 -Compress
