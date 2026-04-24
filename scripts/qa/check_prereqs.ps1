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
$snippetProbeDir = Join-Path $resolvedCodexRoot '.newbiz2-probe'
$snippetProbe = Join-Path $snippetProbeDir 'write-test.tmp'

$checks = @()

$checks += [pscustomobject]@{
    key = 'powershell'
    ok = (Test-CommandExists -Name 'pwsh') -or (Test-CommandExists -Name 'powershell')
    detail = 'Requires PowerShell or pwsh to run the repo scripts.'
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
