param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')
. (Join-Path $PSScriptRoot '..\common\invoke_json_jobs.ps1')

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

trap {
    if ($null -ne $state -and $null -ne $context) {
        $state.status.assets = 'failed'
        $state.gates.gate_5_assets = 'failed'
        $state.gates.gate_5a_source_badges = 'failed'
        Set-StateProperty -Object $state.gates -Name 'gate_5b_required_logos' -Value 'failed'
        & $context.save_run_state -Path $context.run_state_path -State $state
    }
    throw
}

$state.status.assets = 'in_progress'
$state.gates.gate_5_assets = 'in_progress'
$state.gates.gate_5a_source_badges = 'in_progress'
Set-StateProperty -Object $state.gates -Name 'gate_5b_required_logos' -Value 'in_progress'
Add-NewBizHybridEvent -State $state -Type fanout -Key 'assets.logo_acquisition' -Jobs @(
    'required-logo-manifest:brand',
    'required-logo-manifest:competitors',
    'required-logo-manifest:news_sources'
) -Notes @('Logo candidates must be acquired and checked before source badge validation and asset validation run.')
& $context.save_run_state -Path $context.run_state_path -State $state

$requiredLogos = & (Join-Path $PSScriptRoot 'build_required_logo_manifest.ps1') -DataPath $context.data_path -AcquireMissing -NoDataWrite | ConvertFrom-Json
if ($requiredLogos.ok -ne $true) {
    throw ("Required logo acquisition failed: {0}" -f (@($requiredLogos.warnings) -join '; '))
}

$assetPatchManifest = [string]$requiredLogos.report_data_patch_manifest
if ([string]::IsNullOrWhiteSpace($assetPatchManifest) -or -not (Test-Path -LiteralPath $assetPatchManifest)) {
    throw 'Required logo acquisition did not produce an assets report-data patch manifest.'
}
$assetReduction = & (Join-Path $PSScriptRoot '..\common\apply_report_data_manifest.ps1') -DataPath $context.data_path -ManifestPath $assetPatchManifest -Domain 'assets' | ConvertFrom-Json
if ($assetReduction.ok -ne $true) {
    throw 'Assets report-data reducer failed.'
}

Add-NewBizHybridEvent -State $state -Type fanout -Key 'assets.source_badges' -Jobs @(
    'source-badge-manifest',
    'brand-asset-validation',
    'delivery-asset-validation'
) -Notes @('Source badge validation and brand asset validation run only after logo acquisition has produced candidate assets.')
& $context.save_run_state -Path $context.run_state_path -State $state

$assetJobs = @(
    @{
        key = 'source_badges'
        path = Join-Path $PSScriptRoot 'build_source_badge_manifest.ps1'
        parameters = @{ DataPath = $context.data_path }
    },
    @{
        key = 'validation'
        path = Join-Path $PSScriptRoot 'validate_brand_assets.ps1'
        parameters = @{ DataPath = $context.data_path }
    },
    @{
        key = 'delivery_assets'
        path = Join-Path $PSScriptRoot 'validate_delivery_assets.ps1'
        parameters = @{ DataPath = $context.data_path }
    }
)
$assetResults = Invoke-JsonJobs -Jobs $assetJobs -WorkingDirectory $context.brand_folder
$sourceBadges = $assetResults.source_badges
$validation = $assetResults.validation
$deliveryAssets = $assetResults.delivery_assets
if ($sourceBadges.ok -ne $true) {
    throw 'Source badge validation failed.'
}
if ($validation.ok -ne $true) {
    throw ("Brand asset validation failed: {0}" -f (@($validation.warnings) -join '; '))
}
if ($deliveryAssets.ok -ne $true) {
    throw 'Delivery asset validation failed.'
}
Add-NewBizHybridEvent -State $state -Type reducer -Key 'assets.asset_manifest_reducer' -Outputs @(
    (Join-Path $context.brand_folder 'required-logo-manifest.json'),
    (Join-Path $context.brand_folder 'source-badge-manifest.json'),
    $assetPatchManifest
) -Notes @(
    'Accepted logo and badge manifests are reduced before asset gates pass.',
    'canonical_writer:apply_report_data_manifest',
    ('new_sha256:{0}' -f [string]$assetReduction.new_sha256)
)

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
    asset_reduction = $assetReduction
    source_badges = $sourceBadges
    validation = $validation
    delivery_assets = $deliveryAssets
} | ConvertTo-Json -Depth 8 -Compress
