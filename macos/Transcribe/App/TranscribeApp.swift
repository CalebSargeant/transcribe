import SwiftUI

@main
struct TranscribeApp: App {
    // One store for the whole app, so the settings window and the library
    // cannot disagree about where the meetings are.
    @State private var settings = Settings()
    @State private var tags = TagIndex()
    @State private var pipeline = Pipeline()

    var body: some Scene {
        WindowGroup {
            LibraryView()
                .frame(minWidth: 900, minHeight: 560)
                .environment(settings)
                .environment(tags)
                .environment(pipeline)
        }
        .windowToolbarStyle(.unified)
        .commands {
            // The app browses a folder; it has no documents to open.
            CommandGroup(replacing: .newItem) {}
        }

        SwiftUI.Settings {
            SettingsView()
                .environment(settings)
        }
    }
}
