import Foundation
import SwiftUI

/// Runs the `transcribe` command line tool on behalf of the app.
///
/// The app deliberately does not reimplement any of the pipeline. Whisper,
/// diarization and the LLM calls all live in the Python, and this shells out to
/// exactly the command a user would type, so there is one implementation and
/// one set of settings behind both.
@MainActor
@Observable
final class Pipeline {
    enum State: Equatable {
        case idle
        case running(String)
        case finished(String)
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var output: String = ""
    private var task: Task<Void, Never>?

    /// Where the CLI might be. A Homebrew install and a local checkout put it
    /// in different places, and the app must not care which the user has.
    static func locate() -> URL? {
        let candidates = [
            "/opt/homebrew/bin/transcribe",
            "/usr/local/bin/transcribe",
            FileManager.default.homeDirectoryForCurrentUser
                .appending(path: ".local/bin/transcribe").path(percentEncoded: false),
            "/opt/homebrew/bin/transcribe-dev",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
            .map { URL(filePath: $0) }
    }

    var isRunning: Bool { if case .running = state { return true } else { return false } }

    func cancel() {
        task?.cancel()
        task = nil
        state = .idle
    }

    /// Reprocess one meeting folder's recording, which regenerates its notes.
    func regenerate(folder: MeetingFolder, media: URL?, label: String) {
        guard let tool = Self.locate() else {
            state = .failed(
                "The transcribe command line tool was not found. Install it with "
                    + "'brew install calebsargeant/tap/transcribe'."
            )
            return
        }
        guard let media else {
            state = .failed("This meeting has no recording to reprocess.")
            return
        }
        run(tool: tool, arguments: [media.path(percentEncoded: false)], label: label)
    }

    private func run(tool: URL, arguments: [String], label: String) {
        cancel()
        state = .running(label)
        output = ""

        task = Task { [weak self] in
            let result = await Self.execute(tool: tool, arguments: arguments)
            guard let self, !Task.isCancelled else { return }
            self.output = result.output
            self.state =
                result.status == 0
                ? .finished(label)
                : .failed("\(label) failed (exit \(result.status)). See the log below.")
        }
    }

    /// Runs the tool and collects its output.
    ///
    /// Reading both pipes concurrently matters: the pipeline is chatty, and a
    /// child that fills the pipe buffer while the parent waits on `exit` is a
    /// deadlock rather than a slow run.
    private nonisolated static func execute(
        tool: URL, arguments: [String]
    ) async -> (status: Int32, output: String) {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = tool
                process.arguments = arguments
                // A GUI app inherits a bare PATH; the pipeline shells out to
                // ffmpeg and whisper, which live where Homebrew put them.
                var environment = ProcessInfo.processInfo.environment
                let path = environment["PATH"] ?? "/usr/bin:/bin"
                environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + path
                process.environment = environment

                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = pipe

                do {
                    try process.run()
                } catch {
                    continuation.resume(returning: (-1, "Could not start: \(error.localizedDescription)"))
                    return
                }

                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                continuation.resume(
                    returning: (
                        process.terminationStatus,
                        String(data: data, encoding: .utf8) ?? ""
                    )
                )
            }
        }
    }
}
