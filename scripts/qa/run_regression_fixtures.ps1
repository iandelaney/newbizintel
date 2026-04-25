param(
    [string]$RepoRoot = '',
    [string[]]$DataPaths = @(),
    [switch]$IncludeWorkspaceGoldens,
    [string]$WorkspaceOutputRoot = 'C:\codex projects\output'
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Invoke-NewBizFixtureJson {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Path,
        [hashtable]$Parameters = @{}
    )

    try {
        $output = & $Path @Parameters
        return [pscustomobject]@{
            name = $Name
            ok = $true
            result = ($output | ConvertFrom-Json)
            error = $null
        }
    }
    catch {
        return [pscustomobject]@{
            name = $Name
            ok = $false
            result = $null
            error = [string]$_.Exception.Message
        }
    }
}

function Add-NewBizFixture {
    param(
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$DataPath,
        [bool]$RequireCanonicalOutput = $false
    )

    if (-not (Test-Path -LiteralPath $DataPath)) {
        return
    }

    $script:fixtures += [pscustomobject]@{
        key = $Key
        data_path = (Resolve-Path -LiteralPath $DataPath).Path
        require_canonical_output = $RequireCanonicalOutput
    }
}

$fixtures = @()

foreach ($path in @($DataPaths)) {
    if ($path) {
        Add-NewBizFixture -Key (Split-Path -Leaf (Split-Path -Parent $path)) -DataPath $path -RequireCanonicalOutput:$true
    }
}

$repoExample = Join-Path $RepoRoot 'examples\report-data.json'
Add-NewBizFixture -Key 'repo-example' -DataPath $repoExample -RequireCanonicalOutput:$false

if ($IncludeWorkspaceGoldens -and (Test-Path -LiteralPath $WorkspaceOutputRoot)) {
    foreach ($brand in @('ocado', 'univers')) {
        Add-NewBizFixture -Key $brand -DataPath (Join-Path $WorkspaceOutputRoot "$brand\report-data.json") -RequireCanonicalOutput:$true
    }
}

$results = @()
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

foreach ($fixture in @($fixtures)) {
    $dataPath = [string]$fixture.data_path
    $brandFolder = Split-Path -Parent $dataPath
    $htmlPath = Join-Path $brandFolder 'newbizintel-report.html'
    $pptxPath = Join-Path $brandFolder 'newbizintel-report.pptx'

    $checks = @()
    $checks += Invoke-NewBizFixtureJson -Name 'intake_identity' -Path (Join-Path $RepoRoot 'scripts\qa\audit_intake_identity.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'schema' -Path (Join-Path $RepoRoot 'scripts\structure\validate_report_data.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'brand_assets' -Path (Join-Path $RepoRoot 'scripts\assets\validate_brand_assets.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'delivery_assets' -Path (Join-Path $RepoRoot 'scripts\assets\validate_delivery_assets.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'required_logos' -Path (Join-Path $RepoRoot 'scripts\assets\build_required_logo_manifest.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'source_badges' -Path (Join-Path $RepoRoot 'scripts\assets\build_source_badge_manifest.ps1') -Parameters @{ DataPath = $dataPath }
    $checks += Invoke-NewBizFixtureJson -Name 'campaign_art_contract' -Path (Join-Path $RepoRoot 'scripts\qa\audit_campaign_art_contract.ps1') -Parameters @{ DataPath = $dataPath }

    if (Test-Path -LiteralPath $htmlPath) {
        $checks += Invoke-NewBizFixtureJson -Name 'presentation' -Path (Join-Path $RepoRoot 'scripts\qa\audit_presentation_layer.ps1') -Parameters @{ HtmlPath = $htmlPath; DataPath = $dataPath }
    }
    else {
        $checks += [pscustomobject]@{
            name = 'presentation'
            ok = $false
            result = $null
            error = "Rendered HTML fixture is missing: $htmlPath"
        }
    }

    if (Test-Path -LiteralPath $pptxPath) {
        $checks += Invoke-NewBizFixtureJson -Name 'pptx' -Path (Join-Path $RepoRoot 'scripts\qa\audit_pptx_output.ps1') -Parameters @{ PptxPath = $pptxPath }
    }
    else {
        $checks += [pscustomobject]@{
            name = 'pptx'
            ok = $false
            result = $null
            error = "PPTX fixture is missing: $pptxPath"
        }
    }

    $runStatePath = Join-Path $brandFolder 'run-state.json'
    if ($fixture.require_canonical_output -and (Test-Path -LiteralPath $runStatePath)) {
        $checks += Invoke-NewBizFixtureJson -Name 'hybrid_execution' -Path (Join-Path $RepoRoot 'scripts\qa\audit_hybrid_execution.ps1') -Parameters @{ DataPath = $dataPath }
        $checks += Invoke-NewBizFixtureJson -Name 'task_list' -Path (Join-Path $RepoRoot 'scripts\qa\audit_task_list.ps1') -Parameters @{ DataPath = $dataPath }
    }
    elseif ($fixture.require_canonical_output) {
        $warnings.Add("Fixture '$($fixture.key)' has no run-state.json; skipped hybrid and task-list audits.")
    }

    if ($fixture.require_canonical_output) {
        $checks += Invoke-NewBizFixtureJson -Name 'output_location' -Path (Join-Path $RepoRoot 'scripts\qa\audit_output_location.ps1') -Parameters @{ DataPath = $dataPath }
    }

    foreach ($check in @($checks)) {
        if ($check.ok -ne $true) {
            $errors.Add("Fixture '$($fixture.key)' failed '$($check.name)': $($check.error)")
        }
        elseif ($check.result -and $check.result.PSObject.Properties['ok'] -and $check.result.ok -ne $true) {
            $errors.Add("Fixture '$($fixture.key)' returned ok:false for '$($check.name)'.")
        }
    }

    $results += [pscustomobject]@{
        key = $fixture.key
        data_path = $dataPath
        require_canonical_output = [bool]$fixture.require_canonical_output
        ok = (@($checks | Where-Object { $_.ok -ne $true }).Count -eq 0)
        checks = $checks
    }
}

if ($fixtures.Count -eq 0) {
    $errors.Add('No regression fixtures were found.')
}

if ($errors.Count -gt 0) {
    throw ("Regression fixture audit failed: {0}" -f ($errors.ToArray() -join '; '))
}

[pscustomobject]@{
    ok = $true
    repo_root = (Resolve-Path -LiteralPath $RepoRoot).Path
    fixture_count = @($fixtures).Count
    fixtures = $results
    warnings = $warnings.ToArray()
} | ConvertTo-Json -Depth 8 -Compress
