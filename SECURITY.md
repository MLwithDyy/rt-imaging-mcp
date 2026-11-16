# Security policy

`rt-imaging-mcp` is a research tool that sits between AI agents and medical image files. Its main job is to
limit what leaves your machine, so reports about leaks are the most valuable ones.

## Reporting a vulnerability

Please use GitHub's private reporting: open the **Security** tab of this repository and choose
**Report a vulnerability**. Do not open a public issue for a security problem.

**Never include real patient data** in a report, not even a single file, screenshot or tag value. Describe the
structure of the file instead, or reproduce the problem with synthetic data (the test suite has generators in
`tests/synthetic.py`).

This is a solo, best-effort project. I will try to acknowledge a report within about a week, but I cannot promise
a fixed timeline.

## What counts as a security issue

- A tool returns something the [threat model](docs/threat-model.md) says it must not return: patient identifiers,
  free text from a file, structure or beam names that are not standardised, UIDs, pixel data, absolute paths or
  coordinates.
- A client can make the server read outside the configured root (path traversal, symlinks) or write, delete,
  move or send anything.
- An error message that contains data read from a file.
- A way to make the server exhaust memory or CPU that the documented limits should have prevented.
- A secret or patient-data-like file in the repository history.

## What does not count

- The known limits listed in the threat model (for example: folder names chosen by the user can contain
  identifiers, prompt injection through file content cannot be fully prevented, results are approximate).
- Problems in the MCP client, the language model, or in how you configured them.
- Using the tool with real patient data on a cloud-hosted model. The documentation tells you not to.

## Supported versions

Only the latest release receives fixes. The project is pre-alpha.
