import SwiftUI

@main
struct TranscribeApp: App {
    var body: some Scene {
        WindowGroup {
            LibraryView()
                .frame(minWidth: 900, minHeight: 560)
        }
        .windowToolbarStyle(.unified)
        .commands {
            // The app browses a folder; it has no documents to open.
            CommandGroup(replacing: .newItem) {}
        }

        Settings {
            SettingsView()
        }
    }
}
