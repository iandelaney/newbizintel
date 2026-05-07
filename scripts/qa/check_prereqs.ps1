param(
    [string]$CodexRoot = ''
)

$ErrorActionPreference = 'Stop'

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-DefaultCodexRoot {
    param([string]$Override)

    if ($Override) { return $Override }
    if ($env:CODEX_HOME) { return $env:CODEX_HOME }
    if ($env:HOME) { return (Join-Path $env:HOME '.codex') }
    return (Join-Path $env:USERPROFILE '.codex')
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$resolvedCodexRoot = [System.IO.Path]::GetFullPath((Get-DefaultCodexRoot -Override $CodexRoot))
$companionRoot = Join-Path $repoRoot 'companion-skills'
$configExample = Join-Path $repoRoot 'codex-config.example.toml'
$snippetProbeDir = Join-Path $resolvedCodexRoot '.newbizintel-probe'
$snippetProbe = Join-Path $snippetProbeDir 'write-test.tmp'

$checks = @()

$legacyPowerShellAvailable = (Test-CommandExists -Name 'pwsh') -or (Test-CommandExists -Name 'powershell')
$checks += [pscustomobject]@{
    key = 'legacy_powershell_renderer'
    ok = $true
    detail = $(if ($legacyPowerShellAvailable) { 'Legacy PowerShell renderer is available.' } else { 'Legacy PowerShell renderer is not available; this is acceptable because Python render_report.py is the default production renderer.' })
}

$checks += [pscustomobject]@{
    key = 'python'
    ok = (Test-CommandExists -Name 'py') -or (Test-CommandExists -Name 'python') -or (Test-CommandExists -Name 'python3')
    detail = 'Requires a usable Python interpreter for runtime and export helpers.'
}

$checks += [pscustomobject]@{
    key = 'node'
    ok = (Test-CommandExists -Name 'node') -and (Test-CommandExists -Name 'npm')
    detail = 'Requires Node.js and npm for native PPTX export via PptxGenJS.'
}

$checks += [pscustomobject]@{
    key = 'companion_skills'
    ok = (Test-Path -LiteralPath $companionRoot)
    detail = "Expected companion-skills folder at $companionRoot."
}

$checks += [pscustomobject]@{
    key = 'config_example'
    ok = (Test-Path -LiteralPath $configExample)
    detail = "Expected config example at $configExample."
}

$checks += [pscustomobject]@{
    key = 'assets'
    ok = (Test-Path -LiteralPath (Join-Path $repoRoot 'assets'))
    detail = "Expected assets folder at $(Join-Path $repoRoot 'assets') for icons, logo helpers, and report presentation assets."
}

$checks += [pscustomobject]@{
    key = 'node_package_manifest'
    ok = (Test-Path -LiteralPath (Join-Path $repoRoot 'package.json')) -and (Test-Path -LiteralPath (Join-Path $repoRoot 'package-lock.json'))
    detail = 'Expected package.json and package-lock.json so npm can install pinned Node dependencies.'
}

$runtimeCheck = Join-Path $repoRoot 'scripts\qa\check_python_runtime.py'
if (Test-Path -LiteralPath $runtimeCheck) {
    try {
        $python = & (Join-Path $repoRoot 'scripts\common\resolve_python.ps1')
        $runtimeRaw = & $python $runtimeCheck --repo-root $repoRoot
        $runtime = $runtimeRaw | ConvertFrom-Json
        $failedRuntimeChecks = @($runtime.checks | Where-Object { -not $_.ok })
        $runtimeDetail = if ($failedRuntimeChecks.Count) {
            ($failedRuntimeChecks | ForEach-Object { $_.detail }) -join '; '
        }
        else {
            'Python runtime dependencies are importable.'
        }
        $checks += [pscustomobject]@{
            key = 'python_runtime_modules'
            ok = [bool]$runtime.ok
            detail = $runtimeDetail
        }
    }
    catch {
        $checks += [pscustomobject]@{
            key = 'python_runtime_modules'
            ok = $false
            detail = "Could not verify Python runtime modules: $($_.Exception.Message)"
        }
    }
}
else {
    $checks += [pscustomobject]@{
        key = 'python_runtime_modules'
        ok = $false
        detail = "Missing Python runtime checker at $runtimeCheck."
    }
}

$writable = $true
$writeError = $null
try {
    New-Item -ItemType Directory -Force -Path $snippetProbeDir | Out-Null
    Set-Content -LiteralPath $snippetProbe -Value 'ok' -Encoding UTF8
    Remove-Item -LiteralPath $snippetProbe -Force -ErrorAction SilentlyContinue
}
catch {
    $writable = $false
    $writeError = $_.Exception.Message
}
finally {
    if (Test-Path -LiteralPath $snippetProbe) {
        Remove-Item -LiteralPath $snippetProbe -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $snippetProbeDir) {
        Remove-Item -LiteralPath $snippetProbeDir -Force -ErrorAction SilentlyContinue
    }
}

$checks += [pscustomobject]@{
    key = 'codex_root_writable'
    ok = $writable
    detail = $(if ($writable) { "Codex root is writable: $resolvedCodexRoot" } else { "Could not write to Codex root ${resolvedCodexRoot}: $writeError" })
}

[pscustomobject]@{
    ok = -not (@($checks | Where-Object { -not $_.ok }).Count)
    repo_root = $repoRoot
    codex_root = $resolvedCodexRoot
    checks = $checks
} | ConvertTo-Json -Depth 6 -Compress
