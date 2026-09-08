# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main`  | Yes       |

This repository has no tagged releases yet; `main` is the supported line.

## Reporting a Vulnerability

Email: **64996768+mcp-tool-shop@users.noreply.github.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Commit affected
- Potential impact

Please report privately rather than opening a public issue.

### Response timeline

| Action | Target |
|--------|--------|
| Acknowledge report | 48 hours |
| Assess severity | 7 days |
| Release fix | 30 days |

## Scope

`portlight-ships` is a dataset and LoRA-training pipeline. It runs **locally only**.

- **No network egress.** Nothing in `pipeline/` or `tools/` opens a socket, issues
  an HTTP request, or contacts a registry. Model weights and the ComfyUI runtime
  are supplied by the operator's own environment; this repository fetches neither.
- **No credentials.** No API keys, tokens, or environment secrets are read,
  stored, or transmitted.
- **No telemetry.**
- **Data touched:** local image and dataset files under `hulls/`, `assets/` and
  the operator's chosen output directories.

**The one boundary worth naming.** Several scripts *emit* ComfyUI workflow JSON;
they do not execute it. That JSON is later run by a separate ComfyUI instance,
which loads models and executes graph nodes with that instance's privileges. A
workflow file is therefore executable input to another program — treat generated
workflows, and any workflow you import from elsewhere, with the same care as a
script. Vulnerabilities in ComfyUI itself, in custom nodes, or in third-party
model weights are out of scope here; report those upstream.

**Also out of scope:** the licensing or provenance of source imagery. That is a
canon and rights question tracked in `docs/`, not a security issue.
