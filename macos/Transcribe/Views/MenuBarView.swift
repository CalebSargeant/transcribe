import SwiftUI

/// The menu bar item: what the detector can see, and a manual override.
///
/// Automatic detection is a guess and always will be. It cannot see a meeting
/// you join with the camera and microphone off, and it occasionally reads
/// something else as a meeting. So the menu carries the two things detection
/// cannot provide: an override that always wins, and the raw signals, so a
/// wrong guess can be understood rather than just endured.
struct MenuBarView: View {
    @Environment(RecordingMonitor.self) private var monitor
    @Environment(Pipeline.self) private var pipeline
    @Environment(WatchQueue.self) private var queue
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Group {
            Text(monitor.status.label)

            Text("Signals: \(monitor.presence.describe)")
                .font(.caption)

            if monitor.status == .detected, let since = monitor.detectedSince {
                Text(waitingText(since: since)).font(.caption)
            }

            Divider()

            if monitor.status == .recording {
                Button("Stop Recording") { stopRecording() }
            } else {
                Button("Record Now") { startRecording() }
                    .disabled(pipeline.isRunning)
            }

            Toggle("Pause Auto-Record", isOn: pausedBinding)

            Divider()

            if !queue.pending.isEmpty {
                Text("\(queue.pending.count) recording(s) not yet processed")
                    .font(.caption)
            }

            Button("Open Transcribe") {
                NSApp.activate(ignoringOtherApps: true)
                openWindow(id: "library")
            }

            Divider()

            Button("Quit") { NSApp.terminate(nil) }
                .keyboardShortcut("q")
        }
    }

    private var pausedBinding: Binding<Bool> {
        Binding(get: { monitor.paused }, set: { monitor.paused = $0 })
    }

    private func waitingText(since: Date) -> String {
        let waited = Int(Date().timeIntervalSince(since))
        return "Detected \(waited)s ago"
    }

    private func startRecording() {
        pipeline.controlRecording(start: true)
        monitor.markRecording(true)
    }

    private func stopRecording() {
        pipeline.controlRecording(start: false)
        monitor.markRecording(false)
    }
}
