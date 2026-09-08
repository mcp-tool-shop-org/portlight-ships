# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

No tagged release yet. `main` carries the 14 ratified hulls, the render and
distillation pipeline, and the workflow builders; history before this file lives
in the git log.

### Added

- `SECURITY.md` recording that the pipeline runs locally with no network egress
  and no credential handling, and naming the one real boundary: the ComfyUI
  workflow JSON it emits is executable input to another program.
