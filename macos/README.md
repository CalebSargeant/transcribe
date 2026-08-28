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

## Not built yet

Recording control. The menu bar app still lives in the Python CLI
(`transcribe menubar`), and moving it here is what would let macOS attach the
calendar and microphone permissions to Transcribe rather than to whichever
terminal launched the CLI. `Info.plist` already carries the usage strings for
it.
