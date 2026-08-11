# Todo 13 frozen diagnostic evidence

Evidence was collected on 2026-08-11 from a Windows 10 22H2 x64
sanitized-reference-host/process. This is not clean/sterile VM evidence.

- Verdict: `go` for frozen dependency closure.
- Bundle-local inventory: 45 files (38 PE binaries and 7 firmware files), all hashed.
- External OS closure: 14 canonical System32 x64 PE files, each allowlisted,
  Microsoft Authenticode-valid, versioned, and SHA-256 recorded.
- Bundled libusb: `_internal/usb1/libusb-1.0.dll`, x64, SHA-256
  `14d03b756ce311f341a009b695c38cf099da442e6674cd4460820512e04ea6fd`.
- Fake mappings passed: device-present, absent, bootloader, firmware-missing,
  and driver-missing.
- Real device: opened non-invasively; firmware was not present. No capture,
  firmware upload, WinUSB/Zadig action, or driver mutation occurred.
- Failure QA: deleting one firmware file from a disposable bundle copy exited 2
  with `ОШИБКА ЗАВИСИМОСТИ: неполный класс firmware: ожидалось 7, найдено 6`
  and no traceback.
- Full suite: 359 tests passed.

Authoritative runtime files are under
`C:\Users\Kirill\Documents\InputLag\.omo\start-work\evidence\task-13-lnt-complete-redesign\`:
`frozen-stdout.txt`, `probe-report.json`, `dependency-inventory.json`,
`verdict.json`, and `failure-qa/stdout.txt`.
