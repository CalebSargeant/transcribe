import Foundation

/// One meeting folder on disk.
///
/// Split in two on purpose. The name and the date are all the sidebar needs and
/// both come out of the folder name, so a list can be drawn without touching
/// the filesystem at all. Everything else costs a directory listing, which on
/// iCloud Drive means a round trip to the file provider: 105 folders measured
/// at 13 seconds of wall clock for 0.14s of CPU. Doing that before first paint
/// left the window on a spinner.
struct MeetingFolder: Identifiable, Hashable, Sendable {
    let id: URL
    let name: String
    let date: Date?

    /// Nil until the folder has been listed. See ``MeetingLibrary/contents(of:)``.
    var contents: Contents?

    struct Contents: Hashable, Sendable {
        var notesJSON: URL?
        var transcriptText: URL?
        var summaryText: URL?
        var notesHTML: URL?
        var media: URL?

        /// A directory with neither notes nor a transcript is something else
        /// that happens to live in the meetings folder.
        var isMeeting: Bool { notesJSON != nil || transcriptText != nil }

        /// Folders written before the JSON pipeline carry only a transcript and
        /// a summary. They are the bulk of an existing library, so they stay
        /// browsable rather than being hidden for lacking structure.
        var isLegacy: Bool { notesJSON == nil }
    }

    /// The folder name with its timestamp stripped, since the sidebar shows the
    /// date separately. Covers this pipeline's two prefixes and Teams'
    /// `Title-20241112_123724-Meeting Recording`, whose stamp and boilerplate
    /// suffix are both noise in a list.
    var displayName: String {
        var trimmed = Self.datePrefix.stringByReplacingMatches(
            in: name,
            range: NSRange(name.startIndex..., in: name),
            withTemplate: ""
        )
        trimmed = Self.teamsSuffix.stringByReplacingMatches(
            in: trimmed,
            range: NSRange(trimmed.startIndex..., in: trimmed),
            withTemplate: ""
        )
        trimmed = trimmed.trimmingCharacters(in: .whitespaces)
        return trimmed.isEmpty ? name : trimmed
    }

    private static let datePrefix = try! NSRegularExpression(
        pattern: "^\\d{4}-\\d{2}-\\d{2}[ T](\\d{2}-\\d{2}-\\d{2}|\\d{4})?\\s*"
    )

    private static let teamsSuffix = try! NSRegularExpression(
        pattern: "[-_]\\d{8}_\\d{6}[-_]Meeting Recording$"
    )
}

/// Scans a directory of meeting folders.
///
/// Two passes. The first lists the root and is enough to draw the sidebar. The
/// second fills in each folder's files in the background, at which point the
/// badges settle and anything that turned out not to be a meeting drops out.
/// Selecting a folder resolves that one immediately rather than waiting for the
/// pass to reach it.
@MainActor
@Observable
final class MeetingLibrary {
    enum Phase: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    private(set) var folders: [MeetingFolder] = []
    private(set) var phase: Phase = .idle
    private(set) var enriching = false
    var root: URL?

    /// Stamps each load so a slow one that finishes after a newer one cannot
    /// overwrite it. `@MainActor` serialises access to the properties, not the
    /// body of an async method, which is released at every await.
    private var loadID = 0
    private var enrichTask: Task<Void, Never>?

    func load(root: URL?) async {
        loadID += 1
        let id = loadID
        enrichTask?.cancel()
        self.root = root

        guard let root else {
            folders = []
            phase = .failed("No meetings folder configured.")
            return
        }

        phase = .loading
        let found = await Task.detached(priority: .userInitiated) {
            Self.scan(root: root)
        }.value

        guard id == loadID else { return }
        folders = found
        phase =
            found.isEmpty
            ? .failed("Nothing in \(root.path(percentEncoded: false)).")
            : .loaded

        guard !found.isEmpty else { return }
        enrichTask = Task { await enrich(id: id) }
    }

    /// Lists every folder's files, a few at a time, updating the list as each
    /// lands. Bounded because the file provider serves these one round trip at
    /// a time and queueing all 105 at once buys nothing.
    private func enrich(id: Int) async {
        enriching = true
        defer { if id == loadID { enriching = false } }

        let batchSize = 8
        var index = 0
        while index < folders.count {
            guard id == loadID, !Task.isCancelled else { return }

            let batch = folders[index..<min(index + batchSize, folders.count)].map(\.id)
            let resolved = await withTaskGroup(of: (URL, MeetingFolder.Contents).self) { group in
                for url in batch {
                    group.addTask { (url, Self.listContents(of: url)) }
                }
                var results: [URL: MeetingFolder.Contents] = [:]
                for await (url, contents) in group { results[url] = contents }
                return results
            }

            guard id == loadID, !Task.isCancelled else { return }
            for position in folders.indices where folders[position].contents == nil {
                if let contents = resolved[folders[position].id] {
                    folders[position].contents = contents
                }
            }
            index += batchSize
        }

        guard id == loadID, !Task.isCancelled else { return }
        // Only now is it known which directories were never meetings.
        folders.removeAll { $0.contents?.isMeeting == false }
        if folders.isEmpty, let root {
            phase = .failed("No meeting folders in \(root.path(percentEncoded: false)).")
        }
    }

    /// The files in one folder, listing it now if the background pass has not
    /// reached it yet. Selecting a meeting must not wait for the queue.
    func contents(of folder: MeetingFolder) async -> MeetingFolder.Contents {
        if let contents = folder.contents { return contents }
        let url = folder.id
        let contents = await Task.detached(priority: .userInitiated) {
            Self.listContents(of: url)
        }.value
        if let position = folders.firstIndex(where: { $0.id == url }) {
            folders[position].contents = contents
        }
        return contents
    }

    /// Reads one folder's `notes.json`. Off the main actor: the file runs to
    /// hundreds of kilobytes and parses hundreds of segments.
    nonisolated static func loadRecord(_ url: URL?) async throws -> MeetingRecord? {
        guard let url else { return nil }
        return try await Task.detached(priority: .userInitiated) {
            let data = try Data(contentsOf: url)
            return try PipelineDate.decoder().decode(MeetingRecord.self, from: data)
        }.value
    }

    nonisolated static func loadText(_ url: URL?) async -> String? {
        guard let url else { return nil }
        return await Task.detached(priority: .userInitiated) {
            try? String(contentsOf: url, encoding: .utf8)
        }.value
    }

    // MARK: - Scanning

    // nonisolated because the scan runs off the main actor. Without it this is a
    // warning today and a hard error under the Swift 6 language mode.
    private nonisolated static let mediaExtensions: Set<String> = [
        "mov", "mp4", "m4a", "qta", "wav", "mp3",
    ]

    /// Lists the root only. No per-folder IO, so this stays fast on a network
    /// or cloud volume.
    nonisolated static func scan(root: URL) -> [MeetingFolder] {
        let manager = FileManager.default
        guard
            let entries = try? manager.contentsOfDirectory(
                at: root,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )
        else { return [] }

        let folders = entries.compactMap { entry -> MeetingFolder? in
            guard
                (try? entry.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true
            else { return nil }
            return MeetingFolder(
                id: entry,
                name: entry.lastPathComponent,
                date: folderDate(from: entry.lastPathComponent),
                contents: nil
            )
        }

        return folders.sorted { lhs, rhs in
            switch (lhs.date, rhs.date) {
            case let (left?, right?): return left > right
            case (nil, _?): return false
            case (_?, nil): return true
            case (nil, nil): return lhs.name > rhs.name
            }
        }
    }

    nonisolated static func listContents(of folder: URL) -> MeetingFolder.Contents {
        guard
            let files = try? FileManager.default.contentsOfDirectory(
                at: folder,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            )
        else { return MeetingFolder.Contents() }

        let bySuffix = { (suffix: String) in
            files.first { $0.lastPathComponent.hasSuffix(suffix) }
        }

        return MeetingFolder.Contents(
            notesJSON: files.first { $0.lastPathComponent == "notes.json" },
            transcriptText: files.first { $0.lastPathComponent == "transcript.txt" }
                ?? bySuffix("_transcription.txt"),
            summaryText: files.first { $0.lastPathComponent == "summary.txt" }
                ?? bySuffix("_summary.txt"),
            notesHTML: files.first { $0.lastPathComponent == "notes.html" },
            media: files
                .filter { mediaExtensions.contains($0.pathExtension.lowercased()) }
                // Prefer video over the extracted audio sitting beside it.
                .sorted {
                    ($0.pathExtension.lowercased() == "wav" ? 1 : 0)
                        < ($1.pathExtension.lowercased() == "wav" ? 1 : 0)
                }
                .first
        )
    }

    /// The date is read from the folder name rather than from the filesystem,
    /// whose creation dates do not survive an iCloud sync.
    ///
    /// Three naming schemes are in the wild, and the third is the majority of
    /// an existing library: this pipeline's `2026-08-27 1105 Title`, its older
    /// `2024-10-30 11-04-23 Title`, and Teams' own
    /// `Title-20241112_123724-Meeting Recording`, which carries its date in
    /// the middle rather than at the front.
    nonisolated static func folderDate(from name: String) -> Date? {
        for format in ["yyyy-MM-dd HHmm", "yyyy-MM-dd HH-mm-ss", "yyyy-MM-dd"] {
            if let date = formatter(format).date(from: String(name.prefix(format.count))) {
                return date
            }
        }
        if let match = embeddedStamp.firstMatch(
            in: name, range: NSRange(name.startIndex..., in: name)
        ), let range = Range(match.range(at: 1), in: name) {
            return formatter("yyyyMMdd_HHmmss").date(from: String(name[range]))
        }
        return nil
    }

    nonisolated static let embeddedStamp = try! NSRegularExpression(
        pattern: "[-_](\\d{8}_\\d{6})[-_]"
    )

    private nonisolated static func formatter(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = format
        return formatter
    }
}
