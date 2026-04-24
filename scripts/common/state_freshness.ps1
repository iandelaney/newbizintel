function Ensure-StateProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
}

function Set-StatePropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [object]$Value
    )

    Ensure-StateProperty -Object $Object -Name $Name -Value $Value
    $Object.$Name = $Value
}

function Ensure-RunStateShape {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State
    )

    Ensure-StateProperty -Object $State -Name 'freshness' -Value ([pscustomobject]@{})
    Ensure-StateProperty -Object $State.freshness -Name 'research_summary_hash' -Value ''
    Ensure-StateProperty -Object $State.freshness -Name 'report_data_hash' -Value ''
    Ensure-StateProperty -Object $State.freshness -Name 'stale_reason' -Value ''

    Ensure-StateProperty -Object $State.gates -Name 'gate_6a_editorial_quality' -Value 'pending'
}

function Set-RunStateStale {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State,

        [Parameter(Mandatory = $true)]
        [string[]]$Statuses,

        [Parameter(Mandatory = $true)]
        [string[]]$Gates,

        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    Ensure-RunStateShape -State $State

    foreach ($statusName in $Statuses) {
        Set-StatePropertyValue -Object $State.status -Name $statusName -Value 'stale'
    }

    foreach ($gateName in $Gates) {
        Set-StatePropertyValue -Object $State.gates -Name $gateName -Value 'stale'
    }

    $State.freshness.stale_reason = $Reason
}

function Update-ResearchSummaryFreshness {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State,

        [Parameter(Mandatory = $true)]
        [string]$SummaryPath
    )

    Ensure-RunStateShape -State $State

    $hash = (Get-FileHash -LiteralPath $SummaryPath -Algorithm SHA256).Hash
    $previous = [string]$State.freshness.research_summary_hash

    if ((-not [string]::IsNullOrWhiteSpace($previous)) -and $previous -ne $hash) {
        Set-RunStateStale -State $State `
            -Statuses @('structure', 'assets', 'campaign_art', 'render', 'qa', 'deploy') `
            -Gates @('gate_4_report_data', 'gate_5_assets', 'gate_5a_source_badges', 'gate_5b_campaign_art', 'gate_6_render_outputs', 'gate_6a_editorial_quality', 'gate_7_delivery') `
            -Reason 'research-summary changed; rerun structure and downstream modules.'
    }

    $State.freshness.research_summary_hash = $hash
}

function Update-ReportDataFreshness {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State,

        [Parameter(Mandatory = $true)]
        [string]$DataPath
    )

    Ensure-RunStateShape -State $State

    $hash = (Get-FileHash -LiteralPath $DataPath -Algorithm SHA256).Hash
    $previous = [string]$State.freshness.report_data_hash

    if ((-not [string]::IsNullOrWhiteSpace($previous)) -and $previous -ne $hash) {
        Set-RunStateStale -State $State `
            -Statuses @('assets', 'campaign_art', 'render', 'qa', 'deploy') `
            -Gates @('gate_5_assets', 'gate_5a_source_badges', 'gate_5b_campaign_art', 'gate_6_render_outputs', 'gate_6a_editorial_quality', 'gate_7_delivery') `
            -Reason 'report-data changed; rerun assets, campaign art, render, QA, and delivery.'
    }

    $State.freshness.report_data_hash = $hash
}
