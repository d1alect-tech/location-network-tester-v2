# ECharts Heatmap Benchmark Decision

## Benchmark Results
| Cells | Render (ms) | Zoom (ms) | Teardown (ms) | Wire Bytes | Heap Used (MiB) | Heap Total (MiB) | Browser RSS (MiB) |
|---|---|---|---|---|---|---|---|
| 64000 | 125.3 | 19.6 | 1.4 | 768000 | 36.6 | 61.9 | 283.4 |
| 128000 | 125.9 | 16.2 | 0.7 | 1536000 | 65.4 | 113.7 | 356.8 |
| 262000 | 170.8 | 16.5 | 0.8 | 3144000 | 142.3 | 193.9 | 445.9 |
| 524000 | 315.1 | 23.0 | 0.7 | 6288000 | 175.8 | 220.5 | 509.4 |
| 2000000 | 1184.6 | 52.9 | 0.7 | 24000000 | 614.3 | 654.0 | 945.4 |

## Decision
- **Hard Viewport-Cell Cap**: 524000 cells
- **Data Format**: Float32Array typed-array layout (X, Y, Value interleaved) for maximum efficiency and minimal wire size.
