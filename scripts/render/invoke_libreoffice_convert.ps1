param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$Format = 'pdf',

    [string]$FilterName,

    [int]$TimeoutSeconds = 120,

    [switch]$KeepProfile
)

$ErrorActionPreference = 'Stop'

function ConvertTo-FileUri {
    param([string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $normalized = $resolved -replace '\\', '/'
    if ($normalized -notmatch '^/') {
        $normalized = '/' + $normalized
    }
    return 'file:///' + $normalized.TrimStart('/')
}

$resolvedInputPath = (Resolve-Path -LiteralPath $InputPath).Path
$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

$sofficeCandidates = @(
    'C:\Program Files\LibreOffice\program\soffice.com',
    'C:\Program Files\LibreOffice\program\soffice.exe'
)
$sofficePath = $sofficeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $sofficePath) {
    $command = Get-Command soffice -ErrorAction SilentlyContinue
    if ($command) {
        $sofficePath = $command.Source
    }
}
if (-not $sofficePath) {
    throw 'LibreOffice was not found. Expected soffice.com or soffice.exe to be installed.'
}

$profileRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'newbizintel-libreoffice'
$profilePath = Join-Path $profileRoot ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $profilePath | Out-Null
$profileUri = ConvertTo-FileUri -Path $profilePath

$convertTarget = if ([string]::IsNullOrWhiteSpace($FilterName)) {
    $Format
}
else {
    '{0}:{1}' -f $Format, $FilterName
}

$arguments = @(
    '--headless',
    '--invisible',
    '--nologo',
    '--nodefault',
    '--nolockcheck',
    '--norestore',
    "-env:UserInstallation=$profileUri",
    '--convert-to', $convertTarget,
    '--outdir', $resolvedOutputDir,
    $resolvedInputPath
)

try {
    $process = Start-Process -FilePath $sofficePath -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
    if (-not $process.HasExited) {
        try {
            $process.WaitForExit($TimeoutSeconds * 1000) | Out-Null
        }
        catch {
        }
    }

    if (-not $process.HasExited) {
        try {
            Stop-Process -Id $process.Id -Force
        }
        catch {
        }
        throw "LibreOffice conversion timed out after $TimeoutSeconds seconds."
    }

    if ($process.ExitCode -ne 0) {
        throw "LibreOffice conversion failed with exit code $($process.ExitCode)."
    }
}
finally {
    if (-not $KeepProfile) {
        Remove-Item -LiteralPath $profilePath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$outputBaseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedInputPath)
$outputPath = Join-Path $resolvedOutputDir ($outputBaseName + '.' + $Format)
if (-not (Test-Path -LiteralPath $outputPath)) {
    throw "LibreOffice reported success but did not create the expected output: $outputPath"
}

[pscustomobject]@{
    ok = $true
    input = $resolvedInputPath
    output = $outputPath
    soffice = $sofficePath
    format = $Format
    profile = $(if ($KeepProfile) { $profilePath } else { $null })
} | ConvertTo-Json -Depth 4 -Compress
