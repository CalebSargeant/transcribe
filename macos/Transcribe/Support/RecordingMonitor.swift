import SwiftUI

/// Watches for a meeting and drives recording, from the menu bar.
///
/// Detection is native, so the microphone and camera checks are attributed to
/// this app rather than to whichever terminal launched the CLI. Starting and
/// stopping OBS is still the CLI's job: it already speaks obs-websocket, and a
/// second implementation of that in Swift would be one more thing to keep in
/// step for no gain.
@MainActor
@Observable
final class RecordingMonitor {
    enum Status: Equatable {
        case idle
        case detected
        case recording
        case paused

        var symbol: String {
            switch self {
            case .idle: "circle.dotted"
            case .detected: "circle"
            case .recording: "record.circle.fill"
            case .paused: "pause.circle"
            }
        }

        var label: String {
            switch self {
            case .idle: "Idle"
            case .detected: "Meeting detected"
            case .recording: "Recording"
            case .paused: "Auto-record paused"
            }
        }
    }

    private(set) var presence = Presence.State()
    private(set) var status: Status = .idle
    private(set) var detectedSince: Date?
    var paused = false {
        didSet { if paused { detectedSince = nil } }
    }

    private var timer: Task<Void, Never>?
    private let settings: Settings

    init(settings: Settings) {
        self.settings = settings
    }

    /// A meeting needs the microphone plus one corroborating signal, unless the
    /// user has said the microphone alone is enough.
    ///
    /// Turning the camera requirement *off* used to make detection impossible:
    /// the old shape returned true only when the requirement was on and the
    /// camera was in use, so relaxing it removed the only route to true.
    var meetingInProgress: Bool {
        guard presence.microphone else { return false }
        if settings.config.bool(ConfigKey.micOnly, default: false) { return true }
        if presence.camera { return true }
        // With the camera not required, a calendar event corroborates instead.
        if !settings.config.bool(ConfigKey.requireCamera, default: true),
            settings.config.bool(ConfigKey.useCalendar, default: true),
            presence.calendarMeeting
        {
            return true
        }
        return false
    }

    func start(pollSeconds: Int = 5) {
        timer?.cancel()
        timer = Task { [weak self] in
            while !Task.isCancelled {
                await self?.tick()
                try? await Task.sleep(for: .seconds(max(pollSeconds, 1)))
            }
        }
    }

    func stop() {
        timer?.cancel()
        timer = nil
    }

    private func tick() async {
        presence = await MeetingLibrary.offMainActor { Presence.current() }

        guard !paused else {
            status = .paused
            return
        }
        if status == .recording { return }

        if meetingInProgress {
            if detectedSince == nil { detectedSince = Date() }
            status = .detected
        } else {
            detectedSince = nil
            status = .idle
        }
    }

    /// How long a meeting has been detected, against the configured delay.
    var readyToRecord: Bool {
        guard let detectedSince else { return false }
        let delay = Double(settings.config.int(ConfigKey.startAfter, default: 45))
        return Date().timeIntervalSince(detectedSince) >= delay
    }

    func markRecording(_ isRecording: Bool) {
        status = isRecording ? .recording : (meetingInProgress ? .detected : .idle)
    }
}
