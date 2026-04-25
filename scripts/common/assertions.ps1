function Assert-NewBizOkResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][object]$Result
    )

    if ($null -eq $Result) {
        throw "$Name did not return a result."
    }

    $okProperty = $Result.PSObject.Properties['ok']
    if ($okProperty -and ($Result.ok -ne $true)) {
        $details = @()
        foreach ($propertyName in @('errors', 'missing', 'failures', 'warnings')) {
            $property = $Result.PSObject.Properties[$propertyName]
            if ($property -and $property.Value) {
                $details += @($property.Value)
            }
        }

        $detailText = @($details | Where-Object { $_ } | ForEach-Object { [string]$_ }) -join '; '
        if (-not $detailText) {
            $detailText = 'no diagnostic details returned'
        }

        throw "$Name failed: $detailText"
    }
}

function Assert-NewBizPath {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Path
    )

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        throw "$Name was not created at the expected path: $Path"
    }
}
