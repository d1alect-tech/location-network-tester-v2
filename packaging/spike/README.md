# Frozen Hantek diagnostic spike

Run from Windows PowerShell 5.1:

```powershell
.\packaging\spike\build-and-probe.ps1 -Evidence <evidence-directory>
```

The script builds a PyInstaller `onedir` executable, inventories recursive PE
imports, verifies bundle-local firmware/binaries, validates allowlisted external
System32 DLLs (canonical path, x64 PE, Microsoft Authenticode, version and
SHA-256), and runs the executable with Python environment variables removed and
a minimal Windows PATH.

This is **sanitized-reference-host/process evidence**, not evidence from a clean
or sterile VM. The probe calls only `lnt.ui.device.diagnose_device()` and fake
adapters. It does not capture, upload firmware, install/change WinUSB, invoke
Zadig, or copy Windows DLLs into the bundle.

`verdict.json` separates dependency closure (`go|no_go`) from real-hardware F3
availability. An absent real device cannot approve F3.
