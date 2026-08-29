import SwiftUI

@main
struct TranscribeApp: App {
    // One store each, shared by every window and the menu bar, so nothing can
    // disagree about where the meetings are or what is in them.
    @State private var settings: Settings
    @State private var monitor: RecordingMonitor
    @State private var tags = TagIndex()
    @State private var index = MeetingIndex()
    @State private var pipeline = Pipeline()
    @State private var queue = WatchQueue()
    @State private var completions = Completions()
    @State private var appleExport = AppleExport()
    @State private var library = MeetingLibrary()
    @State private var commands = AppCommands()

    init() {
        // The monitor reads live settings, so both are built here rather than
        // as separate defaults that would each load the file.
        let settings = Settings()
        _settings = State(initialValue: settings)
        _monitor = State(initialValue: RecordingMonitor(settings: settings))
    }

    var body: some Scene {
        WindowGroup(id: "library") {
            LibraryView()
                .frame(minWidth: 900, minHeight: 560)
                .environment(settings)
                .environment(tags)
                .environment(index)
                .environment(pipeline)
                .environment(queue)
                .environment(monitor)
                .environment(completions)
                .environment(appleExport)
                .environment(library)
                .environment(commands)
                .task {
                    // Detection is native so the microphone and camera checks
                    // are attributed to this app, not to whichever terminal
                    // launched the CLI. That is the whole reason for a bundle.
                    monitor.start(
                        pollSeconds: settings.config.int(ConfigKey.pollSeconds, default: 5))
                }
        }
        .windowToolbarStyle(.unified)
        .commands {

            // A native app is keyboard-drivable. Without these the only way to
            // reach anything is the mouse.
            CommandGroup(after: .toolbar) {
                Button("Meetings") { commands.show(.meetings) }
                    .keyboardShortcut("1", modifiers: .command)
                Button("Action Items") { commands.show(.actions) }
                    .keyboardShortcut("2", modifiers: .command)
                Button("Recording Queue") { commands.show(.queue) }
                    .keyboardShortcut("3", modifiers: .command)
                Divider()
                Button("Refresh") { commands.refresh() }
                    .keyboardShortcut("r", modifiers: .command)
            }

            CommandGroup(after: .appInfo) {
                Button("Open Meetings Folder") {
                    if let url = settings.folder(ConfigKey.destination) {
                        NSWorkspace.shared.open(url)
                    }
                }
                Button("Open Watch Folder") {
                    if let url = settings.folder(ConfigKey.watch) {
                        NSWorkspace.shared.open(url)
                    }
                }
            }

            CommandGroup(replacing: .help) {
                Button("Transcribe on GitHub") {
                    if let url = URL(string: "https://github.com/CalebSargeant/transcribe") {
                        NSWorkspace.shared.open(url)
                    }
                }
            }
        }

        MenuBarExtra {
            MenuBarView()
                .environment(settings)
                .environment(pipeline)
                .environment(queue)
                .environment(monitor)
        } label: {
            Image(systemName: monitor.status.symbol)
        }

        SwiftUI.Settings {
            SettingsView()
                .environment(settings)
                .environment(appleExport)
        }
    }
}
