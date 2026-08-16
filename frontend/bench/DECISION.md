# ECharts Heatmap Benchmark Decision

## Benchmark Results
| Cells | Render (ms) | Zoom (ms) | Teardown (ms) | Wire Bytes | Heap Used (MiB) | Heap Total (MiB) | Browser RSS (MiB) |
|---|---|---|---|---|---|---|---|
| 64000 | 123.4 | 23.4 | 2.1 | 768000 | 37.4 | 60.9 | 284.2 |
| 128000 | 132.5 | 39.3 | 1.1 | 1536000 | 48.4 | 122.2 | 361.6 |
| 262000 | 184.0 | 27.0 | 1.0 | 3144000 | 139.7 | 193.5 | 441.2 |
| 524000 | 342.8 | 31.7 | 0.9 | 6288000 | 162.8 | 229.5 | 550.2 |
| 2000000 | 1147.4 | 66.1 | 0.9 | 24000000 | 670.1 | 723.5 | 1012.8 |

## Decision
- **Hard Viewport-Cell Cap**: 262000 cells
- **Data Format**: Float32Array typed-array layout (X, Y, Value interleaved) for maximum efficiency and minimal wire size.
