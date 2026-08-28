import Foundation

/// A recording sitting in the watch folder, and whether it has been processed.
struct PendingRecording: Identifiable, Hashable, Sendable {
    var id: URL { url }
    let url: URL
    let size: Int64
    let modified: Date?
    /// A meeting folder in the destination that came from this file.
    let processedInto: [URL]

    var isProcessed: Bool { !processedInto.isEmpty }

    var sizeText: String {
        ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
}

/// What is waiting in the watch folder.
///
/// Without this the pipeline is a black box: a recording either turns into a
/// meeting or it does not, and there is nowhere to see which. Matching each
/// file against `source_file` in the meetings already written is what makes
/// "this one never got processed" visible.
@MainActor
@Observable
final class WatchQueue {
    private(set) var recordings: [PendingRecording] = []
    private(set) var scanning = false
    private(set) var message: String?

    private var loadID = 0

    private nonisolated static let mediaExtensions: Set<String> = [
        "mov", "mp4", "m4a", "qta", "wav", "mp3", "avi", "mkv", "m4v",
    ]

    var pending: [PendingRecording] { recordings.filter { !$0.isProcessed } }

    func load(watch: URL?, index: [IndexedMeeting], library: [MeetingFolder]) async {
        loadID += 1
        let id = loadID

        guard let watch else {
            recordings = []
            message = "No watch folder configured."
            return
        }

        scanning = true
        defer { if id == loadID { scanning = false } }

        // Which source files already produced a meeting. Read from the folders
        // themselves rather than guessed from names, because the pipeline
        // renames a meeting after what was said in it.
        let folders = library.map(\.id)
        let found = await MeetingLibrary.offMainActor {
            Self.scan(watch: watch, meetingFolders: folders)
        }

        guard id == loadID else { return }
        recordings = found
        message =
            found.isEmpty
            ? "Nothing in \(watch.path(percentEncoded: false))."
            : nil
    }

    nonisolated static func scan(watch: URL, meetingFolders: [URL]) -> [PendingRecording] {
        let manager = FileManager.default
        guard
            let entries = try? manager.contentsOfDirectory(
                at: watch,
                includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey],
                options: [.skipsHiddenFiles]
            )
        else { return [] }

        // basename of every source_file the library records, mapped to the
        // meeting folders it produced.
        var producedBy: [String: [URL]] = [:]
        for folder in meetingFolders {
            let notes = folder.appending(path: "notes.json")
            guard
                let data = try? Data(contentsOf: notes),
                let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let source = object["source_file"] as? String
            else { continue }
            producedBy[URL(filePath: source).lastPathComponent, default: []].append(folder)
        }

        return
            entries
            .filter { mediaExtensions.contains($0.pathExtension.lowercased()) }
            .map { url in
                let values = try? url.resourceValues(forKeys: [
                    .fileSizeKey, .contentModificationDateKey,
                ])
                return PendingRecording(
                    url: url,
                    size: Int64(values?.fileSize ?? 0),
                    modified: values?.contentModificationDate,
                    // The pipeline moves the source in by default, so a file
                    // still here with a meeting naming it was left in place.
                    processedInto: producedBy[url.lastPathComponent] ?? []
                )
            }
            .sorted { ($0.modified ?? .distantPast) > ($1.modified ?? .distantPast) }
    }
}
