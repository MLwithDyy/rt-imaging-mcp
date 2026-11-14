# rt-imaging-mcp

A local, file-based [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI agents
inspect medical images (DICOM, NIfTI) and radiotherapy objects, with PHI-safe output by default.

> **Status: early development (Phase 0).** Nothing is implemented yet. See [docs/threat-model.md](docs/threat-model.md)
> for the design constraints every tool must satisfy.

## Important

- **Research use only. Not a medical device. Not for clinical use.**
- Running the server locally does **not** by itself keep data private: tool output is sent to the model
  the MCP client uses. If that model is hosted in the cloud, so is every tool result.
  See the threat model for how this project limits what tools return.
- Never use real patient data for development or testing.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
