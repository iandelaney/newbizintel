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
$regressionFixtureScript = Join-Path $RepoRoot 'scripts\qa\run_regression_fixtures.ps1'

$portability = Invoke-JsonScript -Path $portabilityScript
Assert-True ($portability.ok -eq $true) 'Portability audit failed.'

$installSmoke = Invoke-JsonScript -Path $installSmokeScript
Assert-True ($installSmoke.ok -eq $true) 'Install smoke test failed.'

$regressionFixtures = Invoke-JsonScript -Path $regressionFixtureScript
Assert-True ($regressionFixtures.ok -eq $true) 'Regression fixture audit failed.'

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
            key = 'regression-fixtures'
            ok = $true
            detail = 'Regression fixtures passed for installable examples.'
        },
        [pscustomobject]@{
            key = 'delivery-gate-note'
            ok = $true
            detail = 'Full delivery gates are validated against canonical output folders, not repo examples.'
        }
    )
    regression_fixtures = $regressionFixtures
    release_checklist = Join-Path $RepoRoot 'references\release-checklist.md'
} | ConvertTo-Json -Depth 10
