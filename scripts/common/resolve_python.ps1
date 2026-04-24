param()

$ErrorActionPreference = 'Stop'

function Test-UsablePythonCommand {
    param([System.Management.Automation.CommandInfo]$CommandInfo)

    if ($null -eq $CommandInfo) {
        return $false
    }

    $source = [string]$CommandInfo.Source
    if ([string]::IsNullOrWhiteSpace($source)) {
        return $false
    }

    if ($source -match '(?i)\\system32\\python\.ps1$') {
        return $false
    }

    return $true
}

$bundledPython = 'C:\Users\iande\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    return $bundledPython
}

$py = Get-Command py -ErrorAction SilentlyContinue
if (Test-UsablePythonCommand $py) {
    return [string]$py.Source
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (Test-UsablePythonCommand $python) {
    return [string]$python.Source
}

$python3 = Get-Command python3 -ErrorAction SilentlyContinue
if (Test-UsablePythonCommand $python3) {
    return [string]$python3.Source
}

throw 'No usable Python interpreter was found. Install Python 3 or provide the bundled Codex runtime.'
