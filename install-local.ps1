param(
    [string]$DestinationRoot = '',
    [string]$CodexRoot = '',
    [switch]$ForceCompanions
)

$ErrorActionPreference = 'Stop'

function Get-CodexRoot {
    if ($CodexRoot) {
        return $CodexRoot
    }
    if ($DestinationRoot) {
        return (Split-Path -Parent $DestinationRoot)
    }
    if ($env:CODEX_HOME) {
        return $env:CODEX_HOME
    }
    if ($env:HOME) {
        return Join-Path $env:HOME '.codex'
    }
    return Join-Path $env:USERPROFILE '.codex'
}

function Update-CodexConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $codexRoot = Get-CodexRoot
    New-Item -ItemType Directory -Path $codexRoot -Force | Out-Null

    $configPath = Join-Path $codexRoot 'config.toml'
    $snippetPath = Join-Path $codexRoot 'newbizintel-config-snippet.toml'
    $examplePath = Join-Path $RepoRoot 'codex-config.example.toml'
    Copy-Item -LiteralPath $examplePath -Destination $snippetPath -Force

    $block = Get-Content -LiteralPath $examplePath -Raw
    $existing = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw } else { '' }

    if (-not $existing.Trim()) {
        Set-Content -LiteralPath $configPath -Value $block
        return [pscustomobject]@{
            config_path = $configPath
            snippet_path = $snippetPath
            status = 'created'
        }
    }

    $signals = @(
        '[mcp_servers.tavily]',
        '[mcp_servers.composio]',
        '[mcp_servers.playwright]',
        '[mcp_servers.openaiDeveloperDocs]',
        'YOUR_TAVILY_API_KEY'
    )

    $hasOverlap = $false
    foreach ($signal in $signals) {
        if ($existing.Contains($signal)) {
            $hasOverlap = $true
            break
        }
    }

    $markerStart = '# >>> newbizintel setup >>>'
    $markerEnd = '# <<< newbizintel setup <<<'

    if (-not $hasOverlap -and -not $existing.Contains($markerStart)) {
        $prefix = if ($existing.EndsWith("`r`n") -or $existing.EndsWith("`n")) { '' } else { [Environment]::NewLine }
        $managedBlock = $prefix + $markerStart + [Environment]::NewLine + $block.TrimEnd() + [Environment]::NewLine + $markerEnd + [Environment]::NewLine
        Set-Content -LiteralPath $configPath -Value ($existing + $managedBlock)
        return [pscustomobject]@{
            config_path = $configPath
            snippet_path = $snippetPath
            status = 'appended'
        }
    }

    return [pscustomobject]@{
        config_path = $configPath
        snippet_path = $snippetPath
        status = 'snippet_only'
    }
}

$repoRoot = $PSScriptRoot
$mainResult = & (Join-Path $repoRoot 'install-skill.ps1') -DestinationRoot $DestinationRoot | ConvertFrom-Json
$companionResult = & (Join-Path $repoRoot 'install-companion-skills.ps1') -DestinationRoot $DestinationRoot -Force:$ForceCompanions | ConvertFrom-Json
$configResult = Update-CodexConfig -RepoRoot $repoRoot

[pscustomobject]@{
    installed = $true
    source = $repoRoot
    main_skill_destination = $mainResult.destination
    python_runtime_bootstrapped = $mainResult.python_runtime_bootstrapped
    companion_destination_root = $companionResult.destination_root
    installed_companion_skills = $companionResult.installed_skills
    skipped_existing_companion_skills = $companionResult.skipped_existing_skills
    companion_force = [bool]$ForceCompanions
    config_status = $configResult.status
    config_path = $configResult.config_path
    snippet_path = $configResult.snippet_path
    next_steps = @(
        'Replace YOUR_TAVILY_API_KEY in your Codex config',
        'Restart Codex'
    )
} | ConvertTo-Json -Depth 5
