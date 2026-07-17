# RenderDoc RDC Export

See `docs/rdc_export_cli.md` for complete Chinese documentation.

```powershell
.\util\rdc_export\rdc-export.ps1 -Capture "D:\Captures\frame.rdc" -Output ".\exports\frame" -Preset analysis
```

Android captures can use RenderDoc remote replay:

```powershell
.\util\rdc_export\rdc-export.ps1 -Capture "D:\Captures\android.rdc" -Output ".\exports\android" -Preset full -Remote "adb://DEVICE_SERIAL"
```

Or use best-effort local SwiftShader replay for data extraction:

```powershell
.\util\rdc_export\rdc-export.ps1 -Capture "D:\Captures\android.rdc" -Output ".\exports\android" -Preset full -ExtraArgs @("--vulkan-software-replay")
```
