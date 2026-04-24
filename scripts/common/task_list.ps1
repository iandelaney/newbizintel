function Get-NewBizTaskDefinitions {
    return @(
        [pscustomobject]@{
            id = 1
            key = 'intake'
            title = 'Intake and workspace'
            gates = @('gate_1_intake')
            trust_test = 'Brand folder, report-data.json, and run-state.json exist.'
        },
        [pscustomobject]@{
            id = 2
            key = 'competitor_set'
            title = 'Competitor set'
            gates = @('gate_2_competitors')
            trust_test = 'Competitor set is present in the research summary or report data.'
        },
        [pscustomobject]@{
            id = 3
            key = 'current_research'
            title = 'Current research and source map'
            gates = @('gate_3_research')
            trust_test = 'Research summary exists with news, reputation/source status, and locked sets.'
        },
        [pscustomobject]@{
            id = 4
            key = 'semrush_seo_evidence'
            title = 'SEMrush and SEO evidence'
            gates = @('gate_3a_semrush')
            trust_test = 'At least two SEO evidence points are available for the report.'
        },
        [pscustomobject]@{
            id = 5
            key = 'report_structure'
            title = 'Report structure and data contract'
            gates = @('gate_4_report_data')
            trust_test = 'report-data.json passes schema validation and freshness is updated.'
        },
        [pscustomobject]@{
            id = 6
            key = 'logos_and_assets'
            title = 'Brand, competitor, and source logos'
            gates = @('gate_5_assets', 'gate_5a_source_badges', 'gate_5b_required_logos')
            trust_test = 'Brand, competitor, and news/source logos resolve without generic fallbacks.'
        },
        [pscustomobject]@{
            id = 7
            key = 'campaign_ideas_and_art'
            title = 'Creative campaign ideas and artwork'
            gates = @('gate_5b_campaign_art')
            trust_test = 'Campaign ideas pass editorial checks and artwork is final raster, not scaffold.'
        },
        [pscustomobject]@{
            id = 8
            key = 'render_outputs'
            title = 'HTML, portable HTML, and PPTX render'
            gates = @('gate_6_render_outputs')
            trust_test = 'Rendered HTML, portable HTML, and PPTX exist and are current.'
        },
        [pscustomobject]@{
            id = 9
            key = 'quality_review'
            title = 'Quality, trust, and presentation QA'
            gates = @('gate_6a_editorial_quality')
            trust_test = 'Editorial, presentation, logo, campaign-art, and PPTX audits pass.'
        },
        [pscustomobject]@{
            id = 10
            key = 'delivery_handoff'
            title = 'Delivery handoff'
            gates = @('gate_7_delivery')
            trust_test = 'Deploy handoff folder is refreshed from the latest report outputs.'
        }
    )
}

function Ensure-NewBizTaskList {
    param([Parameter(Mandatory = $true)][object]$State)

    $definitions = Get-NewBizTaskDefinitions
    $existingByKey = @{}
    foreach ($task in @($State.task_list)) {
        if ($task -and $task.key) {
            $existingByKey[[string]$task.key] = $task
        }
    }

    $tasks = @()
    foreach ($definition in $definitions) {
        $existing = $existingByKey[[string]$definition.key]
        $status = if ($existing -and $existing.status) { [string]$existing.status } else { 'pending' }
        $updatedAt = if ($existing -and $existing.updated_at) { [string]$existing.updated_at } else { $null }
        $evidence = if ($existing -and $existing.evidence) { @($existing.evidence) } else { @() }

        $tasks += [pscustomobject]@{
            id = $definition.id
            key = $definition.key
            title = $definition.title
            status = $status
            gates = @($definition.gates)
            trust_test = $definition.trust_test
            evidence = $evidence
            updated_at = $updatedAt
        }
    }

    if ($null -eq $State.PSObject.Properties['task_list']) {
        $State | Add-Member -NotePropertyName 'task_list' -NotePropertyValue $tasks
    }
    else {
        $State.task_list = $tasks
    }
}

function Set-NewBizTaskStatus {
    param(
        [Parameter(Mandatory = $true)][object]$State,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][ValidateSet('pending','in_progress','passed','blocked','failed')][string]$Status,
        [string[]]$Evidence = @()
    )

    Ensure-NewBizTaskList -State $State
    $task = @($State.task_list | Where-Object { [string]$_.key -eq $Key }) | Select-Object -First 1
    if (-not $task) {
        throw "Unknown NewBiz2 task-list key: $Key"
    }

    $task.status = $Status
    $task.updated_at = [DateTimeOffset]::UtcNow.ToString('o')
    if ($Evidence.Count -gt 0) {
        $task.evidence = @($Evidence)
    }
}

function Sync-NewBizTaskStatusFromGates {
    param([Parameter(Mandatory = $true)][object]$State)

    Ensure-NewBizTaskList -State $State
    foreach ($task in @($State.task_list)) {
        $gateStatuses = @()
        foreach ($gate in @($task.gates)) {
            $property = $State.gates.PSObject.Properties[[string]$gate]
            if ($property) {
                $gateStatuses += [string]$property.Value
            }
        }

        if ($gateStatuses.Count -eq 0) { continue }

        if ($gateStatuses -contains 'failed') {
            $task.status = 'failed'
        }
        elseif ($gateStatuses -contains 'blocked') {
            $task.status = 'blocked'
        }
        elseif ($gateStatuses -contains 'in_progress') {
            $task.status = 'in_progress'
        }
        elseif (@($gateStatuses | Where-Object { $_ -eq 'passed' }).Count -eq $gateStatuses.Count) {
            $task.status = 'passed'
        }
        else {
            $task.status = 'pending'
        }
    }
}
