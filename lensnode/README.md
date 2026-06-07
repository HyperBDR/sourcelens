# LensNode

LensNode is the standalone execution worker for SourceLens. It connects to the
control plane over WebSocket, reports workspace directories and available tasks,
then executes dispatched runs inside its local workspace.

## Development

```bash
docker compose up --build
```

The standalone compose file only starts the LensNode service. Point
`LENSNODE_CONTROL_WS_URL` and `LENSNODE_AI_GATEWAY_URL` at an existing
SourceLens backend.
