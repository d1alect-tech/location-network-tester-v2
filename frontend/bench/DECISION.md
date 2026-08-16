# ECharts Heatmap Benchmark Decision

## Benchmark Results
| Cells | Render (ms) | Zoom (ms) | Teardown (ms) | Wire Bytes | RSS (MiB) |
|---|---|---|---|---|---|
| 64000 | 97.5 | 18.0 | 1.1 | 768000 | 0.0 |
| 128000 | 104.6 | 27.2 | 0.9 | 1536000 | 0.0 |
| 262000 | 159.9 | 23.6 | 0.8 | 3144000 | 0.0 |
| 524000 | 276.4 | 21.2 | 0.7 | 6288000 | 0.0 |
| 2000000 | 1068.6 | 67.2 | 0.7 | 24000000 | 0.0 |

## Decision
- **Hard Viewport-Cell Cap**: 2000000 cells
- **Data Format**: Float32Array typed-array layout (X, Y, Value interleaved) for maximum efficiency and minimal wire size.
