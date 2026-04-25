function Get-NewBizTaskDefinitions {
    return @(
        [pscustomobject]@{
            id = 1
            key = 'intake'
            title = 'Intake and workspace'
            gates = @('gate_1_intake')
            legacy_gates = @()
            trust_test = 'Brand folder, report-data.json, and run-state.json exist.'
        },
        [pscustomobject]@{
            id = 2
            key = 'competitor_set'
            title = 'Competitor set'
            gates = @('gate_2_competitor_set')
            legacy_gates = @('gate_2_competitors')
            trust_test = 'Competitor set is present in the research summary or report data.'
        },
        [pscustomobject]@{
            id = 3
            key = 'current_research'
            title = 'Current research and source map'
            gates = @('gate_3_current_research')
            legacy_gates = @('gate_3_research')
            trust_test = 'Research summary exists with news, reputation/source status, and locked sets.'
        },
        [pscustomobject]@{
            id = 4
            key = 'search_seo_evidence'
            title = 'Search and SEO evidence'
            gates = @('gate_4_search_seo_evidence')
            legacy_gates = @('gate_3a_semrush', 'gate_4_semrush_seo_evidence')
            trust_test = 'At least two SEO evidence points are available, with SEMrush status explicitly recorded as passed, partial, quota-limited, or blocked.'
        },
        [pscustomobject]@{
            id = 5
            key = 'report_structure'
            title = 'Report structure and data contract'
            gates = @('gate_5_report_structure')
            legacy_gates = @('gate_4_report_data')
            trust_test = 'report-data.json passes schema validation and freshness is updated.'
        },
        [pscustomobject]@{
            id = 6
            key = 'logos_and_assets'
            title = 'Brand, competitor, and source logos'
            gates = @('gate_6_logos_and_assets')
            legacy_gates = @('gate_5_assets', 'gate_5a_source_badges', 'gate_5b_required_logos')
            trust_test = 'Brand, competitor, and news/source logos resolve without generic fallbacks.'
        },
        [pscustomobject]@{
            id = 7
            key = 'campaign_ideas_and_art'
            title = 'Creative campaign ideas and artwork'
            gates = @('gate_7_campaign_ideas_and_art')
            legacy_gates = @('gate_5b_campaign_art')
            trust_test = 'Campaign ideas pass editorial checks and artwork is final raster, not scaffold.'
        },
        [pscustomobject]@{
            id = 8
            key = 'render_outputs'
            title = 'HTML, portable HTML, and PPTX render'
            gates = @('gate_8_render_outputs')
            legacy_gates = @('gate_6_render_outputs')
            trust_test = 'Rendered HTML, portable HTML, and PPTX exist and are current.'
        },
        [pscustomobject]@{
            id = 9
            key = 'quality_review'
            title = 'Quality, trust, and presentation QA'
            gates = @('gate_9_quality_review')
            legacy_gates = @('gate_6a_editorial_quality')
            trust_test = 'Editorial, presentation, logo, campaign-art, and PPTX audits pass.'
        },
        [pscustomobject]@{
            id = 10
            key = 'delivery_handoff'
            title = 'Delivery handoff'
            gates = @('gate_10_delivery_handoff')
            legacy_gates = @('gate_7_delivery')
            trust_test = 'Deploy handoff folder is refreshed from the latest report outputs.'
        }
    )
}

function Get-NewBizGateStatusFromAliases {
    param(
        [Parameter(Mandatory = $true)][object]$State,
        [Parameter(Mandatory = $true)][string[]]$GateNames
    )

    $statuses = @()
    foreach ($gateName in @($GateNames)) {
        $property = $State.gates.PSObject.Properties[[string]$gateName]
        if ($property) {
            $statuses += [string]$property.Value
        }
    }

    if ($statuses.Count -eq 0) { return 'pending' }
    if ($statuses -contains 'failed') { return 'failed' }
    if ($statuses -contains 'blocked') { return 'blocked' }
    if ($statuses -contains 'in_progress') { return 'in_progress' }
    if (@($statuses | Where-Object { $_ -eq 'passed' }).Count -eq $statuses.Count) { return 'passed' }
    if ($statuses -contains 'quota-limited') { return 'passed' }
    return 'pending'
}

function Sync-NewBizPrimaryGates {
    param([Parameter(Mandatory = $true)][object]$State)

    if ($null -eq $State.PSObject.Properties['gates'] -or $null -eq $State.gates) {
        $State | Add-Member -NotePropertyName 'gates' -NotePropertyValue ([pscustomobject]@{})
    }

    foreach ($definition in Get-NewBizTaskDefinitions) {
        $primaryGate = [string]@($definition.gates)[0]
        $primaryGateProperty = $State.gates.PSObject.Properties[$primaryGate]
        if (
            $primaryGateProperty -and
            -not [string]::IsNullOrWhiteSpace([string]$primaryGateProperty.Value) -and
            [string]$primaryGateProperty.Value -ne 'pending'
        ) {
            continue
        }

        $aliasGates = @($definition.legacy_gates | ForEach-Object { [string]$_ })
        $allGateNames = $(if ($aliasGates.Count -gt 0) { $aliasGates } else { @($primaryGate) })
        $status = Get-NewBizGateStatusFromAliases -State $State -GateNames $allGateNames

        if ($null -eq $primaryGateProperty) {
            $State.gates | Add-Member -NotePropertyName $primaryGate -NotePropertyValue $status
        }
        else {
            $State.gates.$primaryGate = $status
        }
    }
}

function Ensure-NewBizTaskList {
    param([Parameter(Mandatory = $true)][object]$State)

    Sync-NewBizPrimaryGates -State $State
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
            legacy_gates = @($definition.legacy_gates)
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

    Sync-NewBizPrimaryGates -State $State
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

        $previousStatus = [string]$task.status
        $nextStatus = $previousStatus
        if ($gateStatuses -contains 'failed') {
            $nextStatus = 'failed'
        }
        elseif ($gateStatuses -contains 'blocked') {
            $nextStatus = 'blocked'
        }
        elseif ($gateStatuses -contains 'in_progress') {
            $nextStatus = 'in_progress'
        }
        elseif (@($gateStatuses | Where-Object { $_ -eq 'passed' }).Count -eq $gateStatuses.Count) {
            $nextStatus = 'passed'
        }
        else {
            $nextStatus = 'pending'
        }

        if ($previousStatus -ne $nextStatus) {
            $task.status = $nextStatus
            $task.updated_at = [DateTimeOffset]::UtcNow.ToString('o')
        }

        if ($null -eq $task.PSObject.Properties['evidence']) {
            $task | Add-Member -NotePropertyName 'evidence' -NotePropertyValue @()
        }

        if ($nextStatus -in @('in_progress','passed','blocked','failed')) {
            $previousEvidence = @($task.evidence | ForEach-Object { [string]$_ })
            $nextEvidence = @($task.gates | ForEach-Object {
                $gateName = [string]$_
                $gateProperty = $State.gates.PSObject.Properties[$gateName]
                $gateValue = if ($gateProperty) { [string]$gateProperty.Value } else { 'missing' }
                "$($gateName):$gateValue"
            })
            foreach ($legacyGate in @($task.legacy_gates)) {
                $gateName = [string]$legacyGate
                $gateProperty = $State.gates.PSObject.Properties[$gateName]
                if ($gateProperty) {
                    $nextEvidence += "$($gateName):$([string]$gateProperty.Value)"
                }
            }
            $task.evidence = @($nextEvidence)
            if (
                [string]::IsNullOrWhiteSpace([string]$task.updated_at) -or
                ($previousEvidence -join '|') -ne ($nextEvidence -join '|')
            ) {
                $task.updated_at = [DateTimeOffset]::UtcNow.ToString('o')
            }
        }
    }
}
