param(
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Invoke-JsonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string[]]$Arguments = @()
    )

    $output = & $Path @Arguments
    return ($output | ConvertFrom-Json)
}

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

$portabilityScript = Join-Path $RepoRoot 'scripts\qa\audit_portability.ps1'
$installSmokeScript = Join-Path $RepoRoot 'scripts\qa\smoke_test_install.ps1'
$runnerScript = Join-Path $RepoRoot 'scripts\run_newbiz2.ps1'
$sampleDataPath = Join-Path $RepoRoot 'examples\report-data.json'
$sampleHtmlPath = Join-Path $RepoRoot 'examples\newbizintel-report.html'
$samplePortablePath = Join-Path $RepoRoot 'examples\archive\newbizintel-report-portable.html'
$sampleRunStatePath = Join-Path $RepoRoot 'examples\run-state.json'

$portability = Invoke-JsonScript -Path $portabilityScript
Assert-True ($portability.ok -eq $true) 'Portability audit failed.'

$installSmoke = Invoke-JsonScript -Path $installSmokeScript
Assert-True ($installSmoke.ok -eq $true) 'Install smoke test failed.'

$null = & $runnerScript -DataPath $sampleDataPath -Mode 'full'

Assert-True (Test-Path -LiteralPath $sampleHtmlPath) "Expected sample HTML output at $sampleHtmlPath."
Assert-True (Test-Path -LiteralPath $samplePortablePath) "Expected portable HTML output at $samplePortablePath."
Assert-True (Test-Path -LiteralPath $sampleRunStatePath) "Expected run-state output at $sampleRunStatePath."

[pscustomobject]@{
    ok = $true
    repo_root = $RepoRoot
    checks = @(
        [pscustomobject]@{
            key = 'portability'
            ok = $true
            detail = 'Portability audit passed.'
        },
        [pscustomobject]@{
            key = 'install-smoke'
            ok = $true
            detail = 'Repo-local install smoke test passed.'
        },
        [pscustomobject]@{
            key = 'sample-full-gated-run'
            ok = $true
            detail = 'Sample full gated run produced HTML, portable HTML, and run-state outputs.'
        }
    )
    outputs = [pscustomobject]@{
        sample_html = $sampleHtmlPath
        sample_portable_html = $samplePortablePath
        sample_run_state = $sampleRunStatePath
    }
    release_checklist = Join-Path $RepoRoot 'references\release-checklist.md'
} | ConvertTo-Json -Depth 6
