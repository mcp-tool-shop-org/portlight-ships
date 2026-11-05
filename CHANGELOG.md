# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

No tagged release yet. `main` carries the 14 ratified hulls, the render and
distillation pipeline, and the workflow builders; history before this file lives
in the git log.

### Added

- `hf/portlight-ships-anatomy/README.md` with the Hugging Face dataset card source for `mcp-tool-shop/portlight-ships-anatomy`, adding end-to-end provenance (Nano Banana 2 / Gemini 3.1 Flash Image plates via paid Comfy Cloud → Tripo v3.1 meshes → `normalize_meshes.py` → Blender 5.2 turntable renders → derived captions), CC BY-SA 4.0 attribution for quoted Wikipedia phrases in the `sources:` lines of four canon entries (`barque.md`, `cog.md`, `galley.md`, `junk.md`), explicit MIT licence scope, the `mcp-tool-shop/portlight-ships-anatomy-lora` link, and `imagefolder` viewer YAML configuration.
- `tools/build_hf_metadata.py` and the generated 336-row `hf/portlight-ships-anatomy/metadata.jsonl` (`file_name`, `text`, `hull`, `elevation`, `heading`) pairing all 336 images and captions for the Hugging Face Dataset Viewer.
- `SECURITY.md` recording that the pipeline runs locally with no network egress
  and no credential handling, and naming the one real boundary: the ComfyUI
  workflow JSON it emits is executable input to another program.
