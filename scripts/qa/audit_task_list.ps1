param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

function Test-HasItems {
    param([object]$Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    return @($Value).Count -gt 0
}

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
}

function Resolve-LocalPath {
    param(
        [string]$Base,
        [string]$Relative
    )

    if ([string]::IsNullOrWhiteSpace($Relative)) { return '' }
    if ([System.IO.Path]::IsPathRooted($Relative)) { return $Relative }
    return Join-Path $Base $Relative
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repoRoot 'scripts\common\task_list.ps1')

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$runStatePath = Join-Path $brandFolder 'run-state.json'
$researchSummaryPath = Join-Path $brandFolder 'research-summary.json'
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $runStatePath)) {
    throw "Task-list audit failed: run-state.json not found at $runStatePath"
}

$state = Get-Content -LiteralPath $runStatePath -Raw | ConvertFrom-Json -Depth 100
Ensure-NewBizTaskList -State $state
Sync-NewBizTaskStatusFromGates -State $state
$definitions = Get-NewBizTaskDefinitions
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$summary = if (Test-Path -LiteralPath $researchSummaryPath) {
    Get-Content -LiteralPath $researchSummaryPath -Raw | ConvertFrom-Json -Depth 100
}
else {
    $null
}

$tasks = @($state.task_list | Sort-Object id)
if ($tasks.Count -ne 10) {
    Add-Error "Task list should contain exactly 10 primary steps; found $($tasks.Count)."
}

$expectedKeys = @($definitions | ForEach-Object { [string]$_.key })
$actualKeys = @($tasks | ForEach-Object { [string]$_.key })
foreach ($key in $expectedKeys) {
    if ($actualKeys -notcontains $key) {
        Add-Error "Task list is missing primary step '$key'."
    }
}

$firstNotPassed = $null
foreach ($task in $tasks) {
    if ([string]$task.status -ne 'passed' -and $null -eq $firstNotPassed) {
        $firstNotPassed = $task
    }
    elseif ($null -ne $firstNotPassed -and [string]$task.status -eq 'passed') {
        Add-Error "Task '$($task.key)' is marked passed after earlier task '$($firstNotPassed.key)' is not passed; workflow cannot skip ahead."
    }
}

foreach ($task in $tasks) {
    if ([string]$task.status -ne 'passed') {
        continue
    }

    foreach ($gate in @($task.gates)) {
        $gateProperty = $state.gates.PSObject.Properties[[string]$gate]
        if (-not $gateProperty -or [string]$gateProperty.Value -ne 'passed') {
            Add-Error "Task '$($task.key)' is passed but gate '$gate' is not passed."
        }
    }

    switch ([string]$task.key) {
        'intake' {
            if (-not (Test-Path -LiteralPath $brandFolder)) { Add-Error 'Intake task passed but brand folder is missing.' }
            if (-not (Test-Path -LiteralPath $resolvedDataPath)) { Add-Error 'Intake task passed but report-data.json is missing.' }
            if (-not (Test-Path -LiteralPath $runStatePath)) { Add-Error 'Intake task passed but run-state.json is missing.' }
        }
        'competitor_set' {
            $competitors = @($data.cover.competitors) + @($summary.locked_sets.competitors)
            if (-not (Test-HasItems $competitors)) {
                Add-Error 'Competitor task passed but no competitor set is present.'
            }
        }
        'current_research' {
            if ($null -eq $summary) {
                Add-Error 'Current research task passed but research-summary.json is missing.'
            }
            elseif (-not (Test-HasItems $summary.influential_news) -and -not (Test-HasItems $data.brand_reputation.influential_news)) {
                Add-Error 'Current research task passed but no influential-news evidence is present.'
            }
            $sourceEvidence = @($summary.source_map) + @($data.appendix.source_map) + @($data.appendix.sources_reviewed)
            if (-not (Test-HasItems $sourceEvidence)) {
                Add-Error 'Current research task passed but no source-map or reviewed-source evidence is present.'
            }
        }
        'semrush_seo_evidence' {
            if (@($data.seo_audit.semrush_evidence).Count -lt 2) {
                Add-Error 'SEMrush/SEO task passed but fewer than two SEO evidence points are present in report-data.json.'
            }
        }
        'report_structure' {
            $validation = & (Join-Path $repoRoot 'scripts\structure\validate_report_data.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
            if ($validation.ok -ne $true) {
                Add-Error 'Report-structure task passed but report-data validation did not return ok:true.'
            }
            if ([string]::IsNullOrWhiteSpace([string]$state.freshness.report_data_hash)) {
                Add-Error 'Report-structure task passed but report_data_hash is missing from run-state freshness.'
            }
        }
        'logos_and_assets' {
            foreach ($manifestName in @('required-logo-manifest.json', 'source-badge-manifest.json')) {
                $manifestPath = Join-Path $brandFolder $manifestName
                if (-not (Test-Path -LiteralPath $manifestPath)) {
                    Add-Error "Logo/assets task passed but $manifestName is missing."
                }
                else {
                    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -Depth 100
                    if ($manifest.ok -ne $true) {
                        Add-Error "Logo/assets task passed but $manifestName does not report ok:true."
                    }
                }
            }
        }
        'campaign_ideas_and_art' {
            $campaignArt = & (Join-Path $repoRoot 'scripts\qa\audit_campaign_art_contract.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
            if ($campaignArt.ok -ne $true) {
                Add-Error 'Campaign task passed but campaign-art contract did not return ok:true.'
            }
        }
        'render_outputs' {
            $html = Join-Path $brandFolder 'newbizintel-report.html'
            $portable = Join-Path $brandFolder 'archive\newbizintel-report-portable.html'
            $pptx = Join-Path $brandFolder 'newbizintel-report.pptx'
            foreach ($path in @($html, $portable, $pptx)) {
                if (-not (Test-Path -LiteralPath $path)) {
                    Add-Error "Render task passed but output is missing: $path"
                }
            }
        }
        'quality_review' {
            $presentation = & (Join-Path $repoRoot 'scripts\qa\audit_presentation_layer.ps1') -HtmlPath (Join-Path $brandFolder 'newbizintel-report.html') -DataPath $resolvedDataPath | ConvertFrom-Json
            if ($presentation.ok -ne $true) {
                Add-Error 'Quality task passed but presentation audit did not return ok:true.'
            }
        }
        'delivery_handoff' {
            $handoffIndex = Join-Path $brandFolder 'index.html'
            if (-not (Test-Path -LiteralPath $handoffIndex)) {
                Add-Error 'Delivery task passed but brand-folder handoff index.html is missing.'
            }
        }
    }
}

if ($errors.Count -gt 0) {
    throw ("Task-list audit failed: {0}" -f ($errors.ToArray() -join '; '))
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    run_state = $runStatePath
    passed = @($tasks | Where-Object { [string]$_.status -eq 'passed' }).Count
    total = 10
    tasks = $tasks
    warnings = $warnings.ToArray()
} | ConvertTo-Json -Depth 8 -Compress
