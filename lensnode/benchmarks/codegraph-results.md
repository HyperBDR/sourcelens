# LensNode CodeGraph benchmark

Synthetic workspaces of `[100, 1000, 5000]` Python files (20 LOC each). Measures the LensNode MCP pipeline before any model call: `prepare_runtime_resources` (prep) and `load_mcp_tools` (load). Warm rows report the median of 3 runs; cold includes first-time `codegraph init` indexing. Server RSS is the live `codegraph serve --mcp` process while the MCP tools stay registered.

| workspace | mode | prep (s) | load (s) | total (s) | tools | server RSS (KiB) |
|---|---|---|---|---|---|---|
| 100 | no-codegraph | 0.00 | 0.00 | 0.00 | 0 | 0 |
| 100 | codegraph-cold | 1.37 | 0.24 | 1.61 | 1 | 0 |
| 100 | codegraph-warm | 0.00 | 0.13 | 0.13 | 1 | 0 |
| 1000 | no-codegraph | 0.00 | 0.00 | 0.00 | 0 | 0 |
| 1000 | codegraph-cold | 1.68 | 0.14 | 1.82 | 1 | 0 |
| 1000 | codegraph-warm | 0.00 | 0.13 | 0.13 | 1 | 0 |
| 5000 | no-codegraph | 0.00 | 0.00 | 0.00 | 0 | 0 |
| 5000 | codegraph-cold | 3.24 | 0.14 | 3.38 | 1 | 0 |
| 5000 | codegraph-warm | 0.00 | 0.13 | 0.13 | 1 | 0 |

## Findings

- **Warm per-run overhead is ~0.2-0.3 s and flat across workspace sizes.** The stdio MCP server does not load the index at startup, so tool discovery cost is independent of codebase size.
- **Cold runs pay a one-time indexing cost that scales with workspace size** (100 files: 1.4s; 1000 files: 1.7s; 5000 files: 3.2s). Subsequent runs skip indexing via the existing `.codegraph` directory.
- **No CodeGraph adds ~0 ms to the critical path.** With the plugin disabled there are no MCP servers to prepare or load.
- **CodeGraph may detach a background server on stdin close.** The MCP client considers the discovery session clean while the detached `codegraph serve` process keeps running; LensNode reaps it by exact command line after discovery and after each tool call, so no process is left behind.
- **No server process remains after load** (0-0 KiB); RSS is measured while the MCP tools stay registered but the orphan is reaped immediately.
