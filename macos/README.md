# Transcribe for macOS

A native SwiftUI app for browsing what the pipeline produces: meetings down the
left, notes and transcript on the right, and the recording playing alongside
with the transcript able to seek it.

## Build and run

```sh
cd macos && xcodegen generate && open Transcribe.xcodeproj
```

Or from the command line:

```sh
xcodebuild -project macos/Transcribe.xcodeproj -scheme Transcribe -configuration Release build
```

Tests need no simulator:

```sh
xcodebuild -project macos/Transcribe.xcodeproj -scheme Transcribe -destination 'platform=macOS' test
```

The project file is generated. After adding, renaming or deleting a Swift file,
run `xcodegen generate` and commit the result; a new file on disk is otherwise
absent from the target even though a `swiftc` sweep over the tree passes.

## What it does

* Meetings by month, with categories and search across every transcript, not
  just titles.
* Notes, transcript and recording side by side; any timestamp seeks the video.
* Action items from every meeting in one list, with owners and a done state.
* The watch folder, showing what has and has not been processed.
* A menu bar item showing whether a meeting is detected, with a manual override.
* Every setting the CLI reads, editable.

## How it talks to the pipeline

`notes.json`, which the CLI writes into every meeting folder, is the whole
interface. The app reads it and never imports anything Python. Folders without
one still appear, showing whatever transcript and summary they hold, because
they are most of an existing library.

The meetings folder comes from `destination_directory` in
`~/.transcribe/config.yaml` unless you pick another one, and that file stays the
CLI's to own: the app reads it and never writes it back.

## Deployment target

macOS 14. The version in the typecheck sweep has to match, or the gate stops
enforcing what it exists for:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
xcrun --sdk macosx swiftc -typecheck -target arm64-apple-macosx14.0 \
  -sdk "$(xcrun --sdk macosx --show-sdk-path)" \
  $(find macos/Transcribe -name '*.swift')
```

## Signing

Ad-hoc, which is fine on the machine that built it. Giving it to anyone else
means a Developer ID, a hardened runtime and notarisation, none of which is set
up here.

## Folder access, and why it needs re-granting after a rebuild

Meeting folders usually live in iCloud Drive, which macOS treats as a protected
location. A denied read there does not fail: the process blocks inside `open(2)`
and never returns. The app gives the first listing four seconds and then offers
the open panel, because *picking* the folder is what grants access.

The grant is tied to the app's code signature. Ad-hoc signing produces a new
one on every build, so each rebuild loses it and the panel comes back. Granting
Transcribe **Full Disk Access** once in System Settings avoids that, and a real
Developer ID would fix it properly.

## Running the pipeline

The app never reimplements the pipeline. Generating notes, processing a queued
recording and assigning categories all shell out to the `transcribe` CLI, so
there is one implementation and one set of settings behind both. It is looked
up in the usual Homebrew locations; without it those buttons explain what to
install.

## Not built yet

Automatic recording. The menu bar shows what the detector sees and can start or
stop OBS by hand, but the start/stop *timing* still lives in `transcribe
autorecord`. Detection itself is native here, which is what puts the microphone
and camera grants on Transcribe rather than on whichever terminal launched the
CLI.
