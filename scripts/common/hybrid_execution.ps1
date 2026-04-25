function Set-NewBizObjectProperty {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $Object.$Name = $Value
    }
}

function Ensure-NewBizHybridExecution {
    param([Parameter(Mandatory = $true)][object]$State)

    if ($null -eq $State.PSObject.Properties['execution_model'] -or [string]::IsNullOrWhiteSpace([string]$State.execution_model)) {
        Set-NewBizObjectProperty -Object $State -Name 'execution_model' -Value 'hybrid'
    }

    $requiredFanouts = @(
        'research.evidence_collection',
        'assets.logo_acquisition',
        'assets.source_badges',
        'campaign_art.prep',
        'qa.initial_audits'
    )
    $requiredReducers = @(
        'research.summary_reducer',
        'structure.report_data_reducer',
        'assets.asset_manifest_reducer',
        'campaign_art.asset_manifest_reducer',
        'qa.bundle_reducer'
    )

    if ($null -eq $State.PSObject.Properties['hybrid_execution']) {
        Set-NewBizObjectProperty -Object $State -Name 'hybrid_execution' -Value ([pscustomobject]@{
            required_fanouts = $requiredFanouts
            required_reducers = $requiredReducers
            events = @()
        })
    }

    if ($null -eq $State.hybrid_execution.PSObject.Properties['required_fanouts']) {
        Set-NewBizObjectProperty -Object $State.hybrid_execution -Name 'required_fanouts' -Value $requiredFanouts
    }
    if ($null -eq $State.hybrid_execution.PSObject.Properties['required_reducers']) {
        Set-NewBizObjectProperty -Object $State.hybrid_execution -Name 'required_reducers' -Value $requiredReducers
    }
    if ($null -eq $State.hybrid_execution.PSObject.Properties['events']) {
        Set-NewBizObjectProperty -Object $State.hybrid_execution -Name 'events' -Value @()
    }

    $State.hybrid_execution.required_fanouts = @($requiredFanouts)
    $State.hybrid_execution.required_reducers = @($requiredReducers)
    $State.hybrid_execution.events = @($State.hybrid_execution.events)
}

function Add-NewBizHybridEvent {
    param(
        [Parameter(Mandatory = $true)][object]$State,
        [Parameter(Mandatory = $true)][ValidateSet('fanout','reducer')][string]$Type,
        [Parameter(Mandatory = $true)][string]$Key,
        [string[]]$Jobs = @(),
        [string[]]$Outputs = @(),
        [string[]]$Notes = @()
    )

    Ensure-NewBizHybridExecution -State $State
    $existing = @($State.hybrid_execution.events | Where-Object {
        -not ([string]$_.type -eq $Type -and [string]$_.key -eq $Key)
    })
    $existing += [pscustomobject]@{
        timestamp = [DateTimeOffset]::UtcNow.ToString('o')
        type = $Type
        key = $Key
        jobs = @($Jobs)
        outputs = @($Outputs)
        notes = @($Notes)
    }
    $State.hybrid_execution.events = @($existing)
}

function Test-NewBizHybridExecution {
    param([Parameter(Mandatory = $true)][object]$State)

    Ensure-NewBizHybridExecution -State $State
    $errors = New-Object System.Collections.Generic.List[string]
    $warnings = New-Object System.Collections.Generic.List[string]

    if ([string]$State.execution_model -ne 'hybrid') {
        $errors.Add("execution_model must be 'hybrid'. Current value: $($State.execution_model)")
    }

    $events = @($State.hybrid_execution.events)
    function Get-HybridEvent {
        param([string]$Type, [string]$Key)
        @($events | Where-Object { [string]$_.type -eq $Type -and [string]$_.key -eq $Key }) | Select-Object -Last 1
    }

    function Get-HybridEventTime {
        param([object]$Event)
        if ($null -eq $Event -or [string]::IsNullOrWhiteSpace([string]$Event.timestamp)) {
            return $null
        }
        $parsed = [DateTimeOffset]::MinValue
        $rawTimestamp = [string]$Event.timestamp
        $ok = [DateTimeOffset]::TryParse(
            $rawTimestamp,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind,
            [ref]$parsed
        )
        if ($ok) {
            return $parsed.UtcTicks
        }
        return $null
    }

    function Assert-HybridOrder {
        param(
            [string]$BeforeType,
            [string]$BeforeKey,
            [string]$AfterType,
            [string]$AfterKey,
            [string]$Message
        )

        $before = Get-HybridEvent -Type $BeforeType -Key $BeforeKey
        $after = Get-HybridEvent -Type $AfterType -Key $AfterKey
        if (-not $before -or -not $after) { return }

        $beforeTime = Get-HybridEventTime -Event $before
        $afterTime = Get-HybridEventTime -Event $after
        if ($null -eq $beforeTime -or $null -eq $afterTime) {
            $errors.Add("Hybrid events '$BeforeKey' and '$AfterKey' must have parseable timestamps.")
            return
        }
        if ([int64]$beforeTime -gt [int64]$afterTime) {
            $errors.Add($Message)
        }
    }
    foreach ($key in @($State.hybrid_execution.required_fanouts)) {
        $match = @($events | Where-Object { [string]$_.type -eq 'fanout' -and [string]$_.key -eq [string]$key }) | Select-Object -First 1
        if (-not $match) {
            $errors.Add("Missing required hybrid fan-out event: $key")
        }
        elseif (@($match.jobs).Count -eq 0) {
            $errors.Add("Hybrid fan-out event '$key' recorded no jobs.")
        }
    }

    $qaFanout = @($events | Where-Object { [string]$_.type -eq 'fanout' -and [string]$_.key -eq 'qa.initial_audits' }) | Select-Object -First 1
    if ($qaFanout -and (@($qaFanout.jobs) -notcontains 'intake_identity')) {
        $errors.Add("Hybrid fan-out event 'qa.initial_audits' must include intake_identity.")
    }

    $assetSourceFanout = Get-HybridEvent -Type 'fanout' -Key 'assets.source_badges'
    if ($assetSourceFanout) {
        foreach ($job in @('source-badge-manifest', 'brand-asset-validation', 'delivery-asset-validation')) {
            if (@($assetSourceFanout.jobs) -notcontains $job) {
                $errors.Add("Hybrid fan-out event 'assets.source_badges' must include $job.")
            }
        }
    }

    function Assert-ReducerUsesPatchManifest {
        param(
            [string]$Key,
            [string]$ExpectedManifestLeaf,
            [string]$Message
        )

        $event = Get-HybridEvent -Type 'reducer' -Key $Key
        if (-not $event) { return }

        $outputs = @($event.outputs | ForEach-Object { [string]$_ })
        $notes = @($event.notes | ForEach-Object { [string]$_ })
        $hasPatchManifest = $false
        foreach ($output in $outputs) {
            if ((Split-Path -Leaf $output) -eq $ExpectedManifestLeaf) {
                $hasPatchManifest = $true
                break
            }
        }
        if (-not $hasPatchManifest) {
            $errors.Add($Message)
        }
        if ($notes -notcontains 'canonical_writer:apply_report_data_manifest') {
            $errors.Add("Hybrid reducer event '$Key' must declare canonical_writer:apply_report_data_manifest.")
        }
    }

    foreach ($key in @($State.hybrid_execution.required_reducers)) {
        $match = @($events | Where-Object { [string]$_.type -eq 'reducer' -and [string]$_.key -eq [string]$key }) | Select-Object -First 1
        if (-not $match) {
            $errors.Add("Missing required hybrid reducer event: $key")
        }
        elseif (@($match.outputs).Count -eq 0) {
            $errors.Add("Hybrid reducer event '$key' recorded no outputs.")
        }
    }

    Assert-ReducerUsesPatchManifest -Key 'assets.asset_manifest_reducer' -ExpectedManifestLeaf 'assets-report-data-patch.json' -Message "Asset reducer must include assets-report-data-patch.json so asset fan-out cannot write report-data.json directly."
    $campaignReducer = Get-HybridEvent -Type 'reducer' -Key 'campaign_art.asset_manifest_reducer'
    if ($campaignReducer) {
        $campaignPatchOutput = @($campaignReducer.outputs | Where-Object { (Split-Path -Leaf ([string]$_)) -match '-campaign-report-data-patch\.json$' }) | Select-Object -First 1
        if (-not $campaignPatchOutput) {
            $errors.Add("Campaign-art reducer must include a campaign-report-data-patch.json output so campaign-art fan-out cannot write report-data.json directly.")
        }
        if (@($campaignReducer.notes | ForEach-Object { [string]$_ }) -notcontains 'canonical_writer:apply_report_data_manifest') {
            $errors.Add("Hybrid reducer event 'campaign_art.asset_manifest_reducer' must declare canonical_writer:apply_report_data_manifest.")
        }
    }

    Assert-HybridOrder -BeforeType 'fanout' -BeforeKey 'research.evidence_collection' -AfterType 'reducer' -AfterKey 'research.summary_reducer' -Message "Research reducer must run after research evidence fan-out."
    Assert-HybridOrder -BeforeType 'reducer' -BeforeKey 'research.summary_reducer' -AfterType 'reducer' -AfterKey 'structure.report_data_reducer' -Message "Structure reducer must run after research summary reducer."
    Assert-HybridOrder -BeforeType 'reducer' -BeforeKey 'structure.report_data_reducer' -AfterType 'fanout' -AfterKey 'assets.logo_acquisition' -Message "Asset acquisition must not start before structure has reduced report-data.json."
    Assert-HybridOrder -BeforeType 'fanout' -BeforeKey 'assets.logo_acquisition' -AfterType 'fanout' -AfterKey 'assets.source_badges' -Message "Source badge validation must not fan out before logo acquisition has completed."
    Assert-HybridOrder -BeforeType 'fanout' -BeforeKey 'assets.source_badges' -AfterType 'reducer' -AfterKey 'assets.asset_manifest_reducer' -Message "Asset manifest reducer must run after source badge and asset validation fan-out."
    Assert-HybridOrder -BeforeType 'fanout' -BeforeKey 'campaign_art.prep' -AfterType 'reducer' -AfterKey 'campaign_art.asset_manifest_reducer' -Message "Campaign-art reducer must run after campaign-art prep fan-out."
    Assert-HybridOrder -BeforeType 'reducer' -BeforeKey 'assets.asset_manifest_reducer' -AfterType 'fanout' -AfterKey 'qa.initial_audits' -Message "QA audits must not start before asset manifests have been reduced."
    Assert-HybridOrder -BeforeType 'reducer' -BeforeKey 'campaign_art.asset_manifest_reducer' -AfterType 'fanout' -AfterKey 'qa.initial_audits' -Message "QA audits must not start before campaign-art assets have been reduced."
    Assert-HybridOrder -BeforeType 'fanout' -BeforeKey 'qa.initial_audits' -AfterType 'reducer' -AfterKey 'qa.bundle_reducer' -Message "QA bundle reducer must run after QA initial audits."

    [pscustomobject]@{
        ok = ($errors.Count -eq 0)
        execution_model = [string]$State.execution_model
        required_fanouts = @($State.hybrid_execution.required_fanouts)
        required_reducers = @($State.hybrid_execution.required_reducers)
        event_count = $events.Count
        errors = @($errors)
        warnings = @($warnings)
    }
}
