import SwiftUI

/// A bridge from the menu bar's commands to the window that acts on them.
///
/// `.commands` is attached to the Scene, so it cannot reach a view's `@State`.
/// Rather than scatter `@FocusedValue` through the view tree for three menu
/// items, the command raises a token here and the window observes it.
@MainActor
@Observable
final class AppCommands {
    enum Destination: Equatable {
        case actions
        case queue
    }

    /// Bumped rather than set to a value: two refreshes in a row must both
    /// fire, and an Equatable token that never changes would swallow the second.
    private(set) var refreshToken = 0
    private(set) var destination: Destination?

    func refresh() { refreshToken += 1 }

    func show(_ destination: Destination) {
        // Cleared first so selecting the same destination twice still fires.
        self.destination = nil
        self.destination = destination
    }
}
