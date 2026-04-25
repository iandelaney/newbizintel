param(
    [string]$DataPath,
    [string]$BrandName,
    [string]$BrandFolder,
    [string]$TemplatePath,
    [string]$BaseName = 'newbizintel-report'
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath -BrandName $BrandName -BrandFolder $BrandFolder
$state = $context.state
. (Join-Path $PSScriptRoot '..\common\assertions.ps1')

$state.status.render = 'in_progress'
$state.gates.gate_6_render_outputs = 'in_progress'
& $context.save_run_state -Path $context.run_state_path -State $state

$params = @{
    DataPath = $context.data_path
    BaseName = $BaseName
}
if ($TemplatePath) {
    $params.TemplatePath = $TemplatePath
}

$bundle = & (Join-Path $PSScriptRoot 'build_report_bundle.ps1') @params | ConvertFrom-Json
Assert-NewBizOkResult -Name 'Render schema validation' -Result $bundle.schema_validation
Assert-NewBizOkResult -Name 'Render brand asset validation' -Result $bundle.asset_validation
Assert-NewBizOkResult -Name 'Render delivery asset validation' -Result $bundle.delivery_asset_validation
Assert-NewBizPath -Name 'Rendered HTML' -Path $bundle.html
Assert-NewBizPath -Name 'Rendered PPTX' -Path $bundle.pptx
Assert-NewBizPath -Name 'Portable archive HTML' -Path $bundle.archive.html

$state.status.render = 'passed'
$state.gates.gate_6_render_outputs = 'passed'
& $context.save_run_state -Path $context.run_state_path -State $state

[pscustomobject]@{
    module = 'render'
    data = $context.data_path
    brand_folder = $context.brand_folder
    run_state = $context.run_state_path
    bundle = $bundle
} | ConvertTo-Json -Depth 8 -Compress
