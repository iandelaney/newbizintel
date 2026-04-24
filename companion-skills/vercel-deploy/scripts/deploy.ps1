param(
    [string]$InputPath = '.'
)

$ErrorActionPreference = 'Stop'

$DeployEndpoint = 'https://codex-deploy-skills.vercel.sh/api/deploy'

function Get-Framework {
    param([string]$ProjectPath)

    $packageJsonPath = Join-Path $ProjectPath 'package.json'
    if (-not (Test-Path -LiteralPath $packageJsonPath)) {
        return 'null'
    }

    try {
        $pkg = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
    }
    catch {
        return 'null'
    }

    $deps = @{}
    foreach ($group in @($pkg.dependencies, $pkg.devDependencies)) {
        if ($null -ne $group) {
            $group.PSObject.Properties | ForEach-Object { $deps[$_.Name] = $true }
        }
    }

    function HasDep([string]$name) { return $deps.ContainsKey($name) }
    function HasPrefix([string]$prefix) {
        foreach ($key in $deps.Keys) {
            if ($key.StartsWith($prefix)) { return $true }
        }
        return $false
    }

    if (HasDep 'blitz') { return 'blitzjs' }
    if (HasDep 'next') { return 'nextjs' }
    if (HasDep 'gatsby') { return 'gatsby' }
    if (HasPrefix '@remix-run/') { return 'remix' }
    if (HasPrefix '@react-router/') { return 'react-router' }
    if (HasDep '@tanstack/start') { return 'tanstack-start' }
    if (HasDep 'astro') { return 'astro' }
    if (HasDep '@shopify/hydrogen') { return 'hydrogen' }
    if (HasDep '@sveltejs/kit') { return 'sveltekit-1' }
    if (HasDep 'svelte') { return 'svelte' }
    if (HasDep 'nuxt') { return 'nuxtjs' }
    if (HasDep 'vitepress') { return 'vitepress' }
    if (HasDep 'vuepress') { return 'vuepress' }
    if (HasDep 'gridsome') { return 'gridsome' }
    if (HasDep '@solidjs/start') { return 'solidstart-1' }
    if (HasDep '@docusaurus/core') { return 'docusaurus-2' }
    if (HasPrefix '@redwoodjs/') { return 'redwoodjs' }
    if (HasDep 'hexo') { return 'hexo' }
    if (HasDep '@11ty/eleventy') { return 'eleventy' }
    if (HasDep '@ionic/angular') { return 'ionic-angular' }
    if (HasDep '@angular/core') { return 'angular' }
    if (HasDep '@ionic/react') { return 'ionic-react' }
    if (HasDep 'react-scripts') { return 'create-react-app' }
    if ((HasDep 'ember-cli') -or (HasDep 'ember-source')) { return 'ember' }
    if (HasDep '@dojo/framework') { return 'dojo' }
    if (HasPrefix '@polymer/') { return 'polymer' }
    if (HasDep 'preact') { return 'preact' }
    if (HasDep '@stencil/core') { return 'stencil' }
    if (HasDep 'umi') { return 'umijs' }
    if (HasDep 'sapper') { return 'sapper' }
    if (HasDep 'saber') { return 'saber' }
    if (HasDep 'sanity') { return 'sanity-v3' }
    if (HasPrefix '@sanity/') { return 'sanity' }
    if (HasPrefix '@storybook/') { return 'storybook' }
    if (HasDep '@nestjs/core') { return 'nestjs' }
    if (HasDep 'elysia') { return 'elysia' }
    if (HasDep 'hono') { return 'hono' }
    if (HasDep 'fastify') { return 'fastify' }
    if (HasDep 'h3') { return 'h3' }
    if (HasDep 'nitropack') { return 'nitro' }
    if (HasDep 'express') { return 'express' }
    if (HasDep 'vite') { return 'vite' }
    if (HasDep 'parcel') { return 'parcel' }

    return 'null'
}

function Invoke-HttpCheck {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -MaximumRedirection 0 -ErrorAction Stop
        return [int]$response.StatusCode
    }
    catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code) { return [int]$code }
        return 0
    }
}

$resolvedInput = Resolve-Path -LiteralPath $InputPath
$inputItem = Get-Item -LiteralPath $resolvedInput
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
$stagingDir = Join-Path $tempDir 'staging'
$tarballPath = Join-Path $tempDir 'project.tgz'
$cleanupTemp = $true

New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Write-Error 'Preparing deployment...' -ErrorAction Continue
    $framework = 'null'

    if ($inputItem.PSIsContainer) {
        $projectPath = $inputItem.FullName
        $framework = Get-Framework -ProjectPath $projectPath
        New-Item -ItemType Directory -Path $stagingDir | Out-Null

        Write-Error 'Staging project files...' -ErrorAction Continue
        & tar.exe -C $projectPath --exclude='node_modules' --exclude='.git' --exclude='.env' --exclude='.env.*' -cf - . | & tar.exe -C $stagingDir -xf -
        if ($LASTEXITCODE -ne 0) {
            throw 'Tar staging failed.'
        }

        $packageJsonPath = Join-Path $projectPath 'package.json'
        if (-not (Test-Path -LiteralPath $packageJsonPath)) {
            $htmlFiles = Get-ChildItem -LiteralPath $stagingDir -Filter '*.html' -File
            if ($htmlFiles.Count -eq 1 -and $htmlFiles[0].Name -ne 'index.html') {
                Write-Error "Renaming $($htmlFiles[0].Name) to index.html..." -ErrorAction Continue
                Move-Item -LiteralPath $htmlFiles[0].FullName -Destination (Join-Path $stagingDir 'index.html') -Force
            }
        }

        Write-Error 'Creating deployment package...' -ErrorAction Continue
        & tar.exe -czf $tarballPath -C $stagingDir .
        if ($LASTEXITCODE -ne 0) {
            throw 'Tarball creation failed.'
        }
    }
    elseif ($inputItem.Extension -eq '.tgz') {
        Write-Error 'Using provided tarball...' -ErrorAction Continue
        $tarballPath = $inputItem.FullName
        $cleanupTemp = $false
    }
    else {
        throw 'Input must be a directory or a .tgz file.'
    }

    if ($framework -ne 'null') {
        Write-Error "Detected framework: $framework" -ErrorAction Continue
    }

    Write-Error 'Deploying...' -ErrorAction Continue
    $response = Invoke-RestMethod -Uri $DeployEndpoint -Method Post -Form @{ file = Get-Item -LiteralPath $tarballPath; framework = $framework }

    if ($response.error) {
        throw $response.error
    }

    if (-not $response.previewUrl) {
        throw 'Could not extract preview URL from response.'
    }

    Write-Error 'Deployment started. Waiting for build to complete...' -ErrorAction Continue
    Write-Error "Preview URL: $($response.previewUrl)" -ErrorAction Continue

    $maxAttempts = 60
    for ($attempt = 0; $attempt -lt $maxAttempts; $attempt++) {
        $status = Invoke-HttpCheck -Url $response.previewUrl
        if ($status -eq 200) {
            Write-Error '' -ErrorAction Continue
            Write-Error 'Deployment ready!' -ErrorAction Continue
            break
        }
        if ($status -ge 500 -or $status -eq 404 -or $status -eq 0) {
            Write-Error "Building... (attempt $($attempt + 1)/$maxAttempts, status $status)" -ErrorAction Continue
            Start-Sleep -Seconds 5
            continue
        }

        Write-Error '' -ErrorAction Continue
        Write-Error "Deployment responded with status $status." -ErrorAction Continue
        break
    }

    Write-Error '' -ErrorAction Continue
    Write-Error "Preview URL: $($response.previewUrl)" -ErrorAction Continue
    Write-Error "Claim URL:   $($response.claimUrl)" -ErrorAction Continue
    Write-Error '' -ErrorAction Continue

    $response | ConvertTo-Json -Compress -Depth 10
}
finally {
    if ($cleanupTemp -and (Test-Path -LiteralPath $tempDir)) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}
