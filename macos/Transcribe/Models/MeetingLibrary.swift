import Foundation

/// One meeting folder on disk, as the sidebar needs to know it.
///
/// Deliberately cheap: scanning 100+ folders at launch must not parse 100+
/// `notes.json` files, each of which carries every transcript segment. The
/// record is loaded only when the folder is selected.
struct MeetingFolder: Identifiable, Hashable, Sendable {
    let id: URL
    let name: String
    let date: Date?
    let notesJSON: URL?
    let transcriptText: URL?
    let summaryText: URL?
    let notesHTML: URL?
    let media: URL?

    /// Folders written before the JSON pipeline carry only a transcript and a
    /// summary. They are the bulk of an existing library, so they stay
    /// browsable rather than being hidden for lacking structure.
    var isLegacy: Bool { notesJSON == nil }

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
/// The scan itself is `nonisolated` and returns a plain value so it can run off
/// the main actor; only the published result hops back.
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
    var root: URL?

    /// Stamps each scan so a slow one that finishes after a newer one cannot
    /// overwrite it. `@MainActor` serialises access to the properties, not the
    /// body of an async method, which is released at every await.
    private var scanID = 0

    func load(root: URL?) async {
        scanID += 1
        let id = scanID
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

        guard id == scanID else { return }
        folders = found
        phase = found.isEmpty
            ? .failed("No meeting folders in \(root.path(percentEncoded: false)).")
            : .loaded
    }

    /// Reads one folder's `notes.json`. Off the main actor: the file runs to
    /// hundreds of kilobytes and parses hundreds of segments.
    nonisolated static func loadRecord(_ folder: MeetingFolder) async throws -> MeetingRecord? {
        guard let url = folder.notesJSON else { return nil }
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

    // nonisolated because `scan` runs off the main actor. Without it this is a
    // warning today and a hard error under the Swift 6 language mode.
    private nonisolated static let mediaExtensions: Set<String> = [
        "mov", "mp4", "m4a", "qta", "wav", "mp3",
    ]

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
                (try? entry.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true,
                let files = try? manager.contentsOfDirectory(
                    at: entry,
                    includingPropertiesForKeys: nil,
                    options: [.skipsHiddenFiles]
                )
            else { return nil }

            let name = entry.lastPathComponent
            let byName = { (suffix: String) in
                files.first { $0.lastPathComponent.hasSuffix(suffix) }
            }

            // A folder with neither a transcript nor notes is not a meeting.
            let notesJSON = files.first { $0.lastPathComponent == "notes.json" }
            let transcript = files.first { $0.lastPathComponent == "transcript.txt" }
                ?? byName("_transcription.txt")
            guard notesJSON != nil || transcript != nil else { return nil }

            return MeetingFolder(
                id: entry,
                name: name,
                date: folderDate(from: name),
                notesJSON: notesJSON,
                transcriptText: transcript,
                summaryText: files.first { $0.lastPathComponent == "summary.txt" }
                    ?? byName("_summary.txt"),
                notesHTML: files.first { $0.lastPathComponent == "notes.html" },
                media: files
                    .filter { mediaExtensions.contains($0.pathExtension.lowercased()) }
                    // Prefer video over the extracted audio sitting beside it.
                    .sorted { ($0.pathExtension.lowercased() == "wav" ? 1 : 0) < ($1.pathExtension.lowercased() == "wav" ? 1 : 0) }
                    .first
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
