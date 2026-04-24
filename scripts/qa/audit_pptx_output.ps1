param(
    [Parameter(Mandatory = $true)]
    [string]$PptxPath,

    [int]$MinSlideCount = 6,
    [int]$MinSizeKb = 100
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression.FileSystem

$resolvedPptxPath = (Resolve-Path -LiteralPath $PptxPath).Path
$file = Get-Item -LiteralPath $resolvedPptxPath
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$slideNames = @()
$mediaNames = @()

if ($file.Length -lt ($MinSizeKb * 1024)) {
    $errors.Add(("PPTX file is smaller than expected ({0} KB). Minimum: {1} KB." -f ([Math]::Round($file.Length / 1024, 1)), $MinSizeKb))
}

$zip = [System.IO.Compression.ZipFile]::OpenRead($resolvedPptxPath)
try {
    $entryNames = @($zip.Entries | ForEach-Object { $_.FullName })
    foreach ($required in @('[Content_Types].xml', 'ppt/presentation.xml', 'ppt/_rels/presentation.xml.rels')) {
        if (-not ($entryNames -contains $required)) {
            $errors.Add("PPTX package is missing required entry: $required")
        }
    }

    $slideNames = @($entryNames | Where-Object { $_ -match '^ppt/slides/slide\d+\.xml$' } | Sort-Object)
    $mediaNames = @($entryNames | Where-Object { $_ -match '^ppt/media/' } | Sort-Object)

    if ($slideNames.Count -lt $MinSlideCount) {
        $errors.Add("PPTX should contain at least $MinSlideCount slides. Current count: $($slideNames.Count)")
    }

    if ($mediaNames.Count -eq 0) {
        $warnings.Add('PPTX package contains no media assets; check whether logos, charts, or campaign art were dropped.')
    }

    foreach ($slideName in $slideNames) {
        $entry = $zip.GetEntry($slideName)
        if ($null -eq $entry -or $entry.Length -lt 200) {
            $errors.Add("$slideName is unexpectedly small or unreadable.")
        }
    }
}
finally {
    $zip.Dispose()
}

if ($errors.Count -gt 0) {
    throw ("PPTX audit failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    pptx = $resolvedPptxPath
    size_kb = [Math]::Round($file.Length / 1024, 1)
    slide_count = $slideNames.Count
    media_count = $mediaNames.Count
    warnings = @($warnings)
} | ConvertTo-Json -Depth 4 -Compress
