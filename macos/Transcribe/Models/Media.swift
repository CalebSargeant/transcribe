import Foundation

/// What counts as a recording.
///
/// One list. Two had drifted apart: the library accepted six extensions and the
/// watch queue nine, so a `.mkv` in the watch folder became a meeting whose
/// media the library then could not find.
enum Media {
    static let extensions: Set<String> = [
        "mov", "mp4", "m4v", "m4a", "qta", "wav", "mp3", "avi", "mkv",
    ]

    static func isMedia(_ url: URL) -> Bool {
        extensions.contains(url.pathExtension.lowercased())
    }

    /// Video before audio: an extracted `.wav` usually sits beside the `.mov`
    /// it came from, and the video is what the user means by "the recording".
    static func preferred(from urls: [URL]) -> URL? {
        urls.filter(isMedia).sorted {
            ($0.pathExtension.lowercased() == "wav" ? 1 : 0)
                < ($1.pathExtension.lowercased() == "wav" ? 1 : 0)
        }.first
    }
}
