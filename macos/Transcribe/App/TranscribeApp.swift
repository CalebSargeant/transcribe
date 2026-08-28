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
            // The app browses a folder; it has no documents to open.
            CommandGroup(replacing: .newItem) {}
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
        }
    }
}
