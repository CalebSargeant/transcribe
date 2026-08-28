import SwiftUI

/// Shows where the app is reading from and what the CLI is configured to do.
///
/// Read-only on purpose. `~/.transcribe/config.yaml` is the CLI's file, with
/// comments explaining every key; writing it back from here would strip those
/// comments and put two things in charge of one file.
struct SettingsView: View {
    @AppStorage("meetingsFolderPath") private var storedRoot = ""
    @State private var config = Configuration.load()

    var body: some View {
        Form {
            Section("Meetings folder") {
                LabeledContent("Showing") {
                    Text(effectiveRoot?.path(percentEncoded: false) ?? "Not set")
                        .textSelection(.enabled)
                        .foregroundStyle(effectiveRoot == nil ? .secondary : .primary)
                }
                HStack {
                    Button("Choose…") { choose() }
                    if !storedRoot.isEmpty {
                        Button("Use the CLI's folder") { storedRoot = "" }
                            .help("Fall back to destination_directory in config.yaml")
                    }
                }
                if storedRoot.isEmpty {
                    Text("Following destination_directory from the CLI's config.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("Command line configuration") {
                LabeledContent("File", value: Configuration.path.path(percentEncoded: false))
                LabeledContent(
                    "Destination",
                    value: config.destinationDirectory?.path(percentEncoded: false) ?? "Not set"
                )
                LabeledContent(
                    "Watching",
                    value: config.watchDirectory?.path(percentEncoded: false) ?? "Not set"
                )
                LabeledContent("Notes provider", value: config.llmProvider ?? "Not set")
                HStack {
                    Button("Reload") { config = Configuration.load() }
                    Button("Reveal in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([Configuration.path])
                    }
                }
                Text("Edit this file to change how recordings are processed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .fixedSize(horizontal: false, vertical: true)
    }

    private var effectiveRoot: URL? {
        storedRoot.isEmpty ? config.destinationDirectory : URL(filePath: storedRoot)
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Use Folder"
        panel.directoryURL = effectiveRoot
        guard panel.runModal() == .OK, let url = panel.url else { return }
        storedRoot = url.path(percentEncoded: false)
    }
}

#Preview {
    SettingsView()
}
