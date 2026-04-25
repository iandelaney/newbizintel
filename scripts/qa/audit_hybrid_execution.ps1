param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

$context = & (Join-Path $PSScriptRoot '..\common\get_run_context.ps1') -DataPath $DataPath
. (Join-Path $PSScriptRoot '..\common\hybrid_execution.ps1')

$result = Test-NewBizHybridExecution -State $context.state
if ($result.ok -ne $true) {
    throw ("Hybrid execution audit failed: {0}" -f (@($result.errors) -join '; '))
}

$result | ConvertTo-Json -Depth 8 -Compress
