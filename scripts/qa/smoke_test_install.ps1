param(
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
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

function Test-JsonArrayContains {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Array,
        [Parameter(Mandatory = $true)]
        [string]$Expected
    )

    return ($Array -contains $Expected)
}

$installRoot = Join-Path $RepoRoot 'dist\install-smoke'
$skillsRoot = Join-Path $installRoot 'skills'
$codexRoot = Join-Path $installRoot '.codex'
$mainSkillRoot = Join-Path $skillsRoot 'newbizintel'
$configPath = Join-Path $codexRoot 'config.toml'
$snippetPath = Join-Path $codexRoot 'newbizintel-config-snippet.toml'

if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null

$installScript = Join-Path $RepoRoot 'install-local.ps1'
$prereqScript = Join-Path $RepoRoot 'scripts\qa\check_prereqs.ps1'

$firstRun = & $installScript -DestinationRoot $skillsRoot -CodexRoot $codexRoot | ConvertFrom-Json

Assert-True ($firstRun.installed -eq $true) 'First install run did not report success.'
Assert-True (Test-Path -LiteralPath $mainSkillRoot) "Main skill root was not created at $mainSkillRoot."
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'SKILL.md')) 'Installed main skill is missing SKILL.md.'
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'assets')) 'Installed main skill is missing assets.'
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'scripts')) 'Installed main skill is missing scripts.'
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'package.json')) 'Installed main skill is missing package.json for native PPTX export.'
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'node_modules\pptxgenjs')) 'Installed main skill is missing the local pptxgenjs dependency.'
Assert-True (Test-Path -LiteralPath (Join-Path $mainSkillRoot 'vendor\pptx_runtime\.newbizintel-runtime.json')) 'Installed main skill is missing the Python runtime marker.'
Assert-True (Test-Path -LiteralPath $configPath) "Config file was not created at $configPath."
Assert-True (Test-Path -LiteralPath $snippetPath) "Config snippet was not created at $snippetPath."

foreach ($companion in @('playwright', 'vercel-deploy')) {
    Assert-True (Test-Path -LiteralPath (Join-Path $skillsRoot $companion)) "Missing installed companion skill: $companion."
    Assert-True (Test-JsonArrayContains -Array $firstRun.installed_companion_skills -Expected $companion) "First install did not report companion skill $companion as installed."
}

$configText = Get-Content -LiteralPath $configPath -Raw
$snippetText = Get-Content -LiteralPath $snippetPath -Raw

Assert-True ($configText.Contains('[mcp_servers.tavily]')) 'Installed config is missing Tavily MCP settings.'
Assert-True ($configText.Contains('[mcp_servers.composio]')) 'Installed config is missing Composio MCP settings.'
Assert-True ($configText.Contains('YOUR_TAVILY_API_KEY')) 'Installed config is missing Tavily placeholder guidance.'
Assert-True ($snippetPath.EndsWith('newbizintel-config-snippet.toml')) 'Snippet naming does not reflect newbizintel.'
Assert-True ($firstRun.config_status -in @('created','appended','snippet_only')) 'First install did not report a valid config status.'

$secondRun = & $installScript -DestinationRoot $skillsRoot -CodexRoot $codexRoot | ConvertFrom-Json

Assert-True ($secondRun.installed -eq $true) 'Second install run did not report success.'
Assert-True ($secondRun.config_status -eq 'snippet_only') "Expected second install to leave config in snippet_only state, got $($secondRun.config_status)."

$configTextAfterSecondRun = Get-Content -LiteralPath $configPath -Raw
$markerCount = ([regex]::Matches($configTextAfterSecondRun, [regex]::Escape('# >>> newbizintel setup >>>'))).Count
Assert-True ($markerCount -le 1) 'Config contains duplicate newbizintel managed blocks after rerun.'

$prereq = & $prereqScript -CodexRoot $codexRoot | ConvertFrom-Json
Assert-True ($prereq.ok -eq $true) 'Prerequisite checker did not pass against the repo-local smoke-test Codex root.'
Assert-True (@($prereq.checks | Where-Object { $_.key -eq 'python_runtime_modules' -and $_.ok }).Count -eq 1) 'Prerequisite checker did not verify Python runtime modules.'

[pscustomobject]@{
    ok = $true
    repo_root = $RepoRoot
    install_root = $installRoot
    main_skill_root = $mainSkillRoot
    config_path = $configPath
    snippet_path = $snippetPath
    first_run = [pscustomobject]@{
        config_status = $firstRun.config_status
        installed_companion_skills = $firstRun.installed_companion_skills
    }
    second_run = [pscustomobject]@{
        config_status = $secondRun.config_status
        skipped_existing_companion_skills = $secondRun.skipped_existing_companion_skills
    }
    checks = @(
        'repo-local install completed',
        'main skill files copied',
        'assets copied',
        'Python runtime modules verified',
        'native PPTX package installed',
        'companion skills copied',
        'config and snippet written',
        'Composio and Tavily settings present',
        'second install avoided duplicate managed blocks',
        'repo-local prereq check passed'
    )
} | ConvertTo-Json -Depth 6
