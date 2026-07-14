param(
    [string]$Capture = "C:\Renderdoc\yy_极致_高帧率.rdc",
    [string]$Output = "C:\Renderdoc\yy_极致_高帧率_blender_export",
    [int]$ColourPass = 3,
    [string]$Config = "",
    [string]$Python = "C:\Users\caishuo01\AppData\Local\Programs\Python\Python314\python.exe",
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
    [switch]$NoPerDrawFbx,
    [switch]$Strict
)

$script = Join-Path $PSScriptRoot "rdoc_scene_export.py"
$arguments = @(
    $script,
    "--capture", $Capture,
    "--output", $Output,
    "--colour-pass", $ColourPass,
    "--blender", $Blender
)

if ($Config) {
    $arguments += @("--config", $Config)
}
if ($NoPerDrawFbx) {
    $arguments += "--no-per-draw-fbx"
}
if ($Strict) {
    $arguments += "--strict"
}

& $Python @arguments
exit $LASTEXITCODE
