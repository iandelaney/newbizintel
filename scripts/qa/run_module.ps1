param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')
. (Join-Path $PSScriptRoot '..\common\assertions.ps1')

function Set-StateProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $Object.$Name = $Value
    }
}

Set-StateProperty -Object $state.status -Name 'qa' -Value 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_6_render_outputs' -Value 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_6a_editorial_quality' -Value 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_8_render_outputs' -Value 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_9_quality_review' -Value 'in_progress'
Add-NewBizHybridEvent -State $state -Type fanout -Key 'qa.initial_audits' -Jobs @(
    'intake_identity',
    'schema_validation',
    'asset_validation',
    'delivery_assets',
    'required_logos',
    'source_badges',
    'editorial',
    'campaign_art_contract'
) -Notes @('QA smoke test runs independent audits through Invoke-JsonJobs before render/export checks.')
& $context.save_run_state -Path $context.run_state_path -State $state

$qa = & (Join-Path $PSScriptRoot 'smoke_test_bundle.ps1') -DataPath $context.data_path | ConvertFrom-Json
$intakeIdentity = & (Join-Path $PSScriptRoot 'audit_intake_identity.ps1') -DataPath $context.data_path | ConvertFrom-Json
$outputLocation = & (Join-Path $PSScriptRoot 'audit_output_location.ps1') -DataPath $context.data_path | ConvertFrom-Json
$editorial = $qa.editorial
$campaignArt = $qa.campaign_art_contract
$pptx = $qa.pptx_audit

Assert-NewBizOkResult -Name 'QA smoke test' -Result $qa
Assert-NewBizOkResult -Name 'Intake identity audit' -Result $intakeIdentity
Assert-NewBizOkResult -Name 'Output location audit' -Result $outputLocation
Assert-NewBizOkResult -Name 'Editorial audit' -Result $editorial
Assert-NewBizOkResult -Name 'Campaign art contract audit' -Result $campaignArt
Assert-NewBizOkResult -Name 'PPTX audit' -Result $pptx

Add-NewBizHybridEvent -State $state -Type reducer -Key 'qa.bundle_reducer' -Outputs @(
    [string]$qa.render_html,
    [string]$qa.archive_html,
    [string]$qa.pptx
) -Notes @('QA reduced parallel audit outputs plus render/export checks into the final quality gate.')
& $context.save_run_state -Path $context.run_state_path -State $state

$hybridExecution = & (Join-Path $PSScriptRoot 'audit_hybrid_execution.ps1') -DataPath $context.data_path | ConvertFrom-Json
Assert-NewBizOkResult -Name 'Hybrid execution audit' -Result $hybridExecution

Set-StateProperty -Object $state.status -Name 'qa' -Value 'passed'
Set-StateProperty -Object $state.gates -Name 'gate_6_render_outputs' -Value 'passed'
Set-StateProperty -Object $state.gates -Name 'gate_6a_editorial_quality' -Value 'passed'
Set-StateProperty -Object $state.gates -Name 'gate_8_render_outputs' -Value 'passed'
Set-StateProperty -Object $state.gates -Name 'gate_9_quality_review' -Value 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

try {
    $taskList = & (Join-Path $PSScriptRoot 'audit_task_list.ps1') -DataPath $context.data_path | ConvertFrom-Json
    Assert-NewBizOkResult -Name 'Task-list audit' -Result $taskList
}
catch {
    Set-StateProperty -Object $state.status -Name 'qa' -Value 'failed'
    Set-StateProperty -Object $state.gates -Name 'gate_6a_editorial_quality' -Value 'failed'
    Set-StateProperty -Object $state.gates -Name 'gate_9_quality_review' -Value 'failed'
    & $context.save_run_state -Path $context.run_state_path -State $state
    throw
}

[pscustomobject]@{
    module = 'qa'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    qa = $qa
    editorial = $editorial
    campaign_art_contract = $campaignArt
    intake_identity = $intakeIdentity
    hybrid_execution = $hybridExecution
    output_location = $outputLocation
    task_list = $taskList
    pptx = $pptx
} | ConvertTo-Json -Depth 8 -Compress
