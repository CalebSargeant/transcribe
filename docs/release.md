# Release process

Releases are automated via the **Semantic Release** GitHub Actions workflow
(`.github/workflows/semantic-versioning.yml`). You normally do not tag or build by hand.

> macOS only at runtime; binaries are built for macOS (arm64 + x86_64) and Linux.

## Automated flow

On every push to `main` (or a manual `workflow_dispatch` with a `patch`/`minor`/`major`
bump):

1. **semantic-release** computes the next version from
   [Conventional Commit](https://www.conventionalcommits.org/) messages, creates the tag and
   GitHub release, and reports `released` + `tag` outputs.
2. **build** — if a release happened, PyInstaller builds binaries from `transcribe.spec` on
   the release tag for:
   - `transcribe-macos-arm64`
   - `transcribe-macos-x86_64`
   - `transcribe-linux-x86_64`
   - `transcribe-linux-arm64`
3. **upload** — attaches the four binaries and a `SHA256SUMS` file to the GitHub release.
4. **update-homebrew-tap** — dispatches the `update-sha256.yml` workflow in the
   **MagmaMoose tap** repo with the new version, so the formula's checksums refresh
   automatically.

So, to cut a release, just merge Conventional-Commit-formatted changes into `main`. Use a
`feat:` commit for a minor bump, `fix:` for a patch, and a `!`/`BREAKING CHANGE` for a major.

To force a specific bump, run the workflow manually (Actions → **Semantic Release** → Run
workflow) and pick `patch`, `minor`, or `major`.

## Checklist before merging to main

- [ ] Update `CHANGELOG.md` for the upcoming version.
- [ ] Tests pass: `uv run pytest` (or `pytest`).
- [ ] Lint clean: `uv run ruff check .` (line length 100).
- [ ] Commit messages follow Conventional Commits so the version bumps correctly.

## Local development install

```bash
# With uv (preferred)
uv sync
uv run transcribe --help

# Or with pip (editable, including the Google Drive extra)
pip install -e ".[gdrive]"
transcribe --help
```

System dependencies for local runs:

```bash
brew install whisper-cpp ffmpeg
```

## Building a binary locally

The release workflow uses PyInstaller with `transcribe.spec`. To reproduce locally:

```bash
pip install pyinstaller
pip install -r requirements.txt
pyinstaller --clean transcribe.spec
./dist/transcribe --version
```

## Repos involved

- Source: <https://github.com/CalebSargeant/transcribe>
- Homebrew tap: `MagmaMoose/tap` (consumes the released binaries and `SHA256SUMS`)
