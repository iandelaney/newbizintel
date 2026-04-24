param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state

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

$state.status.assets = 'in_progress'
$state.gates.gate_5_assets = 'in_progress'
$state.gates.gate_5a_source_badges = 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_5b_required_logos' -Value 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$requiredLogos = & (Join-Path $PSScriptRoot 'build_required_logo_manifest.ps1') -DataPath $context.data_path -AcquireMissing | ConvertFrom-Json
$sourceBadges = & (Join-Path $PSScriptRoot 'build_source_badge_manifest.ps1') -DataPath $context.data_path | ConvertFrom-Json
$validation = & (Join-Path $PSScriptRoot 'validate_brand_assets.ps1') -DataPath $context.data_path | ConvertFrom-Json

$state.status.assets = 'passed'
$state.gates.gate_5_assets = 'passed'
$state.gates.gate_5a_source_badges = 'passed'
Set-StateProperty -Object $state.gates -Name 'gate_5b_required_logos' -Value 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'assets'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    required_logos = $requiredLogos
    source_badges = $sourceBadges
    validation = $validation
} | ConvertTo-Json -Depth 8 -Compress
