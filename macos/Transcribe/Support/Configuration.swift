import Foundation

/// Reads the settings the app needs out of `~/.transcribe/config.yaml`.
///
/// The CLI owns that file. This reads a handful of top-level scalars from it
/// rather than pulling in a YAML library for a format that is, at this level,
/// `key: value` per line. Anything nested is ignored on purpose: if the app
/// ever needs a nested key, that is the point to take the dependency rather
/// than to grow this into a half-parser that quietly mis-reads real YAML.
struct Configuration: Sendable {
    var destinationDirectory: URL?
    var watchDirectory: URL?
    var llmProvider: String?

    static let path = FileManager.default
        .homeDirectoryForCurrentUser
        .appending(path: ".transcribe/config.yaml")

    static func load(from url: URL = path) -> Configuration {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            return Configuration()
        }
        let values = scalars(in: text)
        return Configuration(
            destinationDirectory: values["destination_directory"].map { URL(filePath: $0) },
            watchDirectory: values["watch_directory"].map { URL(filePath: $0) },
            llmProvider: values["llm_provider"]
        )
    }

    /// Top-level `key: value` pairs only. Indented lines belong to a nested
    /// structure this does not model, so they are skipped rather than guessed
    /// at — except where they continue the previous value, which YAML allows
    /// and which is not optional to handle.
    ///
    /// A long path is wrapped by most YAML writers:
    ///
    ///     destination_directory: /Users/x/Library/.../60-69
    ///       Work & Career/62 Work files/Meetings
    ///
    /// YAML folds that into one value joined by a single space. Reading only
    /// the first line yields a path that exists nowhere and looks plausible,
    /// which is a far worse failure than reading nothing at all.
    static func scalars(in text: String) -> [String: String] {
        var values: [String: String] = [:]
        let lines = text.split(separator: "\n", omittingEmptySubsequences: false)
        var index = 0

        while index < lines.count {
            let line = lines[index]
            index += 1

            guard let first = line.first, !first.isWhitespace, first != "#" else { continue }
            guard let separator = line.firstIndex(of: ":") else { continue }

            let key = String(line[line.startIndex..<separator])
            var value = String(line[line.index(after: separator)...])

            while index < lines.count, isContinuation(lines[index]) {
                value += " " + lines[index].trimmingCharacters(in: .whitespaces)
                index += 1
            }

            // Strip a trailing comment, but only one introduced by whitespace:
            // a '#' inside a path or a key is part of the value.
            if let hash = value.range(of: " #") {
                value = String(value[value.startIndex..<hash.lowerBound])
            }
            value = value.trimmingCharacters(in: .whitespaces)
            if value.count >= 2, value.hasPrefix("\""), value.hasSuffix("\"") {
                value = String(value.dropFirst().dropLast())
            }
            guard !value.isEmpty else { continue }
            values[key] = value
        }
        return values
    }

    /// An indented line that is neither a nested key nor a list item, so the
    /// only thing it can be is the rest of the value above it.
    private static func isContinuation(_ line: Substring) -> Bool {
        guard let first = line.first, first == " " || first == "\t" else { return false }
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty, !trimmed.hasPrefix("#"), !trimmed.hasPrefix("- ") else {
            return false
        }
        // `nested: value` is a mapping entry; `12:00 standup` is prose that
        // happens to contain a colon, so the space after it is what decides.
        if let colon = trimmed.firstIndex(of: ":") {
            let afterColon = trimmed[trimmed.index(after: colon)...]
            let key = trimmed[trimmed.startIndex..<colon]
            let looksLikeKey = !key.isEmpty && key.allSatisfy {
                $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" || $0 == "."
            }
            if looksLikeKey, afterColon.isEmpty || afterColon.first == " " { return false }
        }
        return true
    }
}
