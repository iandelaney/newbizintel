function Invoke-OneJsonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [string[]]$Arguments = @(),

        [hashtable]$Parameters = @{},

        [string]$WorkingDirectory = ''
    )

    if ($WorkingDirectory) {
        Push-Location -LiteralPath $WorkingDirectory
    }

    try {
        $output = if ($Parameters.Count -gt 0) {
            & $Path @Parameters
        }
        else {
            & $Path @Arguments
        }
        $json = ($output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($json)) {
            throw "JSON script produced no output: $Path"
        }
        return ($json | ConvertFrom-Json)
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Invoke-JsonJobs {
    param(
        [Parameter(Mandatory = $true)]
        [array]$Jobs,

        [string]$WorkingDirectory = '',

        [switch]$Sequential
)

    $results = [ordered]@{}
    if ($Jobs.Count -eq 0) {
        return [pscustomobject]$results
    }

    if ($Sequential -or $Jobs.Count -eq 1) {
        foreach ($jobSpec in $Jobs) {
            $jobParameters = @{}
            if ($jobSpec.parameters) {
                if ($jobSpec.parameters -is [System.Collections.IDictionary]) {
                    foreach ($key in $jobSpec.parameters.Keys) {
                        $jobParameters[[string]$key] = $jobSpec.parameters[$key]
                    }
                }
                else {
                    foreach ($property in @($jobSpec.parameters.PSObject.Properties)) {
                        $jobParameters[$property.Name] = $property.Value
                    }
                }
            }

            $results[$jobSpec.key] = Invoke-OneJsonScript `
                -Path ([string]$jobSpec.path) `
                -Arguments ([string[]]$jobSpec.arguments) `
                -Parameters $jobParameters `
                -WorkingDirectory $WorkingDirectory
        }
        return [pscustomobject]$results
    }

    $runningJobs = @()
    foreach ($jobSpec in $Jobs) {
        $jobParameters = [ordered]@{}
        if ($jobSpec.parameters) {
            if ($jobSpec.parameters -is [System.Collections.IDictionary]) {
                foreach ($key in $jobSpec.parameters.Keys) {
                    $jobParameters[[string]$key] = $jobSpec.parameters[$key]
                }
            }
            else {
                foreach ($property in @($jobSpec.parameters.PSObject.Properties)) {
                    $jobParameters[$property.Name] = $property.Value
                }
            }
        }

        $jobPayload = [pscustomobject]@{
            path = [string]$jobSpec.path
            arguments = @([string[]]$jobSpec.arguments)
            parameters = [pscustomobject]$jobParameters
            working_directory = $WorkingDirectory
        } | ConvertTo-Json -Depth 5 -Compress

        $runningJobs += Start-Job -Name ([string]$jobSpec.key) -ScriptBlock {
            param([string]$PayloadJson)

            $Payload = $PayloadJson | ConvertFrom-Json

            if ($Payload.working_directory) {
                Set-Location -LiteralPath ([string]$Payload.working_directory)
            }

            $scriptParameters = @{}
            if ($Payload.parameters) {
                foreach ($property in @($Payload.parameters.PSObject.Properties)) {
                    $scriptParameters[$property.Name] = $property.Value
                }
            }

            if ($scriptParameters.Count -gt 0) {
                & ([string]$Payload.path) @scriptParameters
            }
            else {
                $scriptArguments = @()
                foreach ($argument in @($Payload.arguments)) {
                    $scriptArguments += [string]$argument
                }
                & ([string]$Payload.path) @scriptArguments
            }
        } -ArgumentList $jobPayload
    }

    try {
        Wait-Job -Job $runningJobs | Out-Null

        foreach ($job in $runningJobs) {
            $receiveErrors = @()
            $output = Receive-Job -Job $job -ErrorAction SilentlyContinue -ErrorVariable receiveErrors
            if ($job.State -ne 'Completed' -or $receiveErrors.Count -gt 0) {
                $errorText = (@($receiveErrors) | ForEach-Object { $_.ToString() }) -join '; '
                if ([string]::IsNullOrWhiteSpace($errorText)) {
                    $errorText = "state=$($job.State)"
                }
                throw "Parallel JSON job '$($job.Name)' failed: $errorText"
            }

            $json = ($output -join [Environment]::NewLine).Trim()
            if ([string]::IsNullOrWhiteSpace($json)) {
                throw "Parallel JSON job '$($job.Name)' produced no output."
            }

            try {
                $results[$job.Name] = $json | ConvertFrom-Json
            }
            catch {
                throw "Parallel JSON job '$($job.Name)' produced invalid JSON: $json"
            }
        }
    }
    finally {
        Remove-Job -Job $runningJobs -Force -ErrorAction SilentlyContinue
    }

    return [pscustomobject]$results
}
