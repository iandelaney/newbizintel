param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

function Resolve-LocalAssetPath {
    param(
        [string]$Value,
        [string]$BaseDir
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    try {
        $uri = [System.Uri]$Value
        if ($uri.IsAbsoluteUri) {
            if ($uri.Scheme -eq 'file') {
                return $uri.LocalPath
            }
            return $null
        }
    }
    catch {
    }

    if ([System.IO.Path]::IsPathRooted($Value)) {
        return $Value
    }

    return Join-Path $BaseDir $Value
}

function Get-SvgAspectRatio {
    param([string]$Path)

    try {
        [xml]$svg = Get-Content -LiteralPath $Path -Raw
        $root = $svg.DocumentElement
        if ($null -eq $root) {
            return $null
        }

        $viewBox = [string]$root.GetAttribute('viewBox')
        if (-not [string]::IsNullOrWhiteSpace($viewBox)) {
            $parts = $viewBox -split '\s+'
            if ($parts.Count -ge 4) {
                $width = [double]$parts[2]
                $height = [double]$parts[3]
                if ($height -gt 0) {
                    return ($width / $height)
                }
            }
        }

        $widthAttr = [string]$root.GetAttribute('width')
        $heightAttr = [string]$root.GetAttribute('height')
        if ($widthAttr -and $heightAttr) {
            $width = [double]([regex]::Match($widthAttr, '[0-9.]+').Value)
            $height = [double]([regex]::Match($heightAttr, '[0-9.]+').Value)
            if ($height -gt 0) {
                return ($width / $height)
            }
        }
    }
    catch {
        return $null
    }

    return $null
}

function Get-ImageAspectRatio {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($ext -eq '.svg') {
        return Get-SvgAspectRatio -Path $Path
    }

    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $image = [System.Drawing.Image]::FromFile($Path)
        try {
            if ($image.Height -gt 0) {
                return ($image.Width / $image.Height)
            }
        }
        finally {
            $image.Dispose()
        }
    }
    catch {
        return $null
    }

    return $null
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$dataDir = Split-Path -Parent $resolvedDataPath
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$brand = $data.brand
$warnings = New-Object System.Collections.Generic.List[string]
$details = [ordered]@{}

$brandSlug = [string]$brand.slug
$logoUrl = [string]$brand.logo_url
$markUrl = [string]$brand.mark_url
$logoPath = Resolve-LocalAssetPath -Value $logoUrl -BaseDir $dataDir
$markPath = Resolve-LocalAssetPath -Value $markUrl -BaseDir $dataDir
$details.logo_url = $logoUrl
$details.mark_url = $markUrl

$autoMarkCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($brandSlug)) {
    $autoMarkCandidates += @(
        (Join-Path $dataDir "slide-assets\$brandSlug-mark.png"),
        (Join-Path $dataDir "slide-assets\$brandSlug-mark.svg"),
        (Join-Path $dataDir "$brandSlug-mark.png"),
        (Join-Path $dataDir "$brandSlug-mark.svg")
    )
}
$autoMarkCandidates += @(
    (Join-Path $dataDir 'slide-assets\mark.png'),
    (Join-Path $dataDir 'slide-assets\mark.svg'),
    (Join-Path $dataDir 'mark.png'),
    (Join-Path $dataDir 'mark.svg')
)
$autoMarkPath = $autoMarkCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$details.auto_mark_path = $autoMarkPath

if (-not [string]::IsNullOrWhiteSpace($logoUrl) -and [string]::IsNullOrWhiteSpace($markUrl) -and -not $autoMarkPath) {
    $warnings.Add('brand.logo_url is set but no brand.mark_url or local *-mark asset was found for square cover/title badges.')
}

if ($logoPath -and (Test-Path -LiteralPath $logoPath)) {
    $logoAspect = Get-ImageAspectRatio -Path $logoPath
    if ($null -ne $logoAspect) {
        $details.logo_aspect_ratio = [Math]::Round($logoAspect, 3)
        if ($logoAspect -ge 1.6 -and [string]::IsNullOrWhiteSpace($markUrl) -and -not $autoMarkPath) {
            $warnings.Add(('brand.logo_url points to a wide asset (aspect ratio {0}) but no square mark asset is available; cover/title badges may render a squashed wordmark.' -f ([Math]::Round($logoAspect, 2))))
        }
    }
}
elseif (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
    $details.logo_path_missing = $logoPath
}

if ($markPath -and -not (Test-Path -LiteralPath $markPath)) {
    $warnings.Add(('brand.mark_url was set but the asset was not found at {0}.' -f $markPath))
}

[pscustomobject]@{
    data = $resolvedDataPath
    ok = ($warnings.Count -eq 0)
    warnings = @($warnings)
    details = [pscustomobject]$details
} | ConvertTo-Json -Depth 6 -Compress
