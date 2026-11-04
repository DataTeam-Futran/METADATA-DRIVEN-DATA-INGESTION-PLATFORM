$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$environmentFile = Join-Path $PSScriptRoot "preprod.env"
$setupConfig = Join-Path $PSScriptRoot "setup.json"
$previousEnvironmentFile = $env:MDIP_ENV_FILE

foreach ($requiredPath in @($python, $environmentFile, $setupConfig)) {
    if (-not (Test-Path $requiredPath -PathType Leaf)) {
        throw "Required PRE-PROD file is missing: $requiredPath"
    }
}

Push-Location $projectRoot
try {
    $env:MDIP_ENV_FILE = $environmentFile

    & $python -m incremental_loading.scripts.dynamic_source_target_setup inspect-schema
    if ($LASTEXITCODE -ne 0) {
        throw "PRE-PROD metastore connectivity or schema validation failed."
    }

    & $python -m incremental_loading.scripts.dynamic_source_target_setup validate --config $setupConfig --non-interactive
    if ($LASTEXITCODE -ne 0) {
        throw "PRE-PROD source/target connectivity or privilege validation failed."
    }

    Write-Host "PRE-PROD metastore, source, and target checks passed."
}
finally {
    Pop-Location
    if ($null -eq $previousEnvironmentFile) {
        Remove-Item Env:MDIP_ENV_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:MDIP_ENV_FILE = $previousEnvironmentFile
    }
}