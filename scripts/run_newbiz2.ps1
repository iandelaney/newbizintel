param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'

$canonicalScript = Join-Path $PSScriptRoot 'run_newbizintel.ps1'
& $canonicalScript @RemainingArgs
