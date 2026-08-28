import Foundation

/// Categories on meetings, stored as `tags.json` inside each meeting folder.
///
/// Per-folder rather than one central index: a meeting folder is already the
/// unit that gets moved, synced and archived, so its labels travel with it. A
/// central file would be one rename away from being wrong, and would not
/// survive the folder being opened on another Mac through iCloud.
///
/// `notes.json` is left alone. That file is the pipeline's output and gets
/// rewritten whenever a meeting is reprocessed, which would silently discard
/// anything the app had added to it.
struct Tags: Codable, Sendable, Equatable {
    var names: [String] = []

    static let filename = "tags.json"

    static func load(in folder: URL) -> Tags {
        let url = folder.appending(path: filename)
        guard
            let data = try? Data(contentsOf: url),
            let tags = try? JSONDecoder().decode(Tags.self, from: data)
        else { return Tags() }
        return tags
    }

    func save(in folder: URL) throws {
        let url = folder.appending(path: Self.filename)
        guard !names.isEmpty else {
            // An empty file is just clutter in a folder the user browses.
            try? FileManager.default.removeItem(at: url)
            return
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(self).write(to: url, options: .atomic)
    }
}

/// Every tag in use across the library, so the sidebar can offer them and the
/// same category is not retyped three different ways.
@MainActor
@Observable
final class TagIndex {
    private(set) var byFolder: [URL: [String]] = [:]

    var allTags: [String] {
        Array(Set(byFolder.values.flatMap { $0 })).sorted {
            $0.localizedCaseInsensitiveCompare($1) == .orderedAscending
        }
    }

    func tags(for folder: URL) -> [String] { byFolder[folder] ?? [] }

    func set(_ tags: [String], for folder: URL) throws {
        let cleaned = Self.normalise(tags)
        byFolder[folder] = cleaned.isEmpty ? nil : cleaned
        try Tags(names: cleaned).save(in: folder)
    }

    func toggle(_ tag: String, for folder: URL) throws {
        var current = tags(for: folder)
        if let index = current.firstIndex(where: { $0.caseInsensitiveCompare(tag) == .orderedSame })
        {
            current.remove(at: index)
        } else {
            current.append(tag)
        }
        try set(current, for: folder)
    }

    /// Reads the tag files. Cheap enough to do for the whole library because
    /// each is a few hundred bytes, but it still runs off the main actor since
    /// the folders may be on iCloud.
    func load(folders: [MeetingFolder]) async {
        let urls = folders.map(\.id)
        let loaded = await MeetingLibrary.offMainActor {
            var result: [URL: [String]] = [:]
            for url in urls {
                let tags = Tags.load(in: url)
                if !tags.names.isEmpty { result[url] = tags.names }
            }
            return result
        }
        byFolder = loaded
    }

    /// Trim, drop blanks, and remove case-insensitive duplicates while keeping
    /// the spelling the user typed first.
    // Pure, so nonisolated: it inherits @MainActor from the class otherwise,
    // which makes it uncallable from a test and from the scan.
    nonisolated static func normalise(_ tags: [String]) -> [String] {
        var seen = Set<String>()
        return tags
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .filter { seen.insert($0.lowercased()).inserted }
    }
}
