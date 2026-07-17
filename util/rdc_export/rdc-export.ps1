param(
    [Parameter(Mandatory = $true)]
    [string]$Capture,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [ValidateSet("metadata", "analysis", "full")]
    [string]$Preset = "analysis",

    [string]$Remote = "",
    [string]$Python = "",
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "rdc_export.py"

if (-not $Python) {
    $preferred = Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"
    if (Test-Path -LiteralPath $preferred) {
        $Python = $preferred
    } else {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if (-not $command) {
            throw "Python was not found. Pass -Python with the Python executable used by renderdoc.pyd."
        }
        $Python = $command.Source
    }
}

$arguments = @(
    $scriptPath,
    $Capture,
    "--output", $Output,
    "--preset", $Preset
)

if ($Remote) {
    $arguments += @("--remote", $Remote)
}
if ($ExtraArgs) {
    $arguments += $ExtraArgs
}

& $Python @arguments
exit $LASTEXITCODE
