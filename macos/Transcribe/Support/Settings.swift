import SwiftUI

/// The settings the app exposes, backed by `~/.transcribe/config.yaml`.
///
/// One store, one file. The app and the CLI read the same settings from the
/// same place, so there is nothing to keep in sync and no second source of
/// truth to disagree with the first.
///
/// Every edit writes through immediately. A settings window with a Save button
/// can be left half-applied; this cannot.
@MainActor
@Observable
final class Settings {
    private(set) var config: Configuration
    private(set) var lastError: String?

    init(config: Configuration = .load()) {
        self.config = config
    }

    func reload() {
        config = .load()
        lastError = nil
    }

    private func set(_ key: String, _ value: String) {
        guard config.values[key] != value else { return }
        config.values[key] = value
        do {
            try Configuration.write([key: value])
            lastError = nil
        } catch {
            lastError =
                "Could not save \(Configuration.path.path(percentEncoded: false)): "
                + error.localizedDescription
        }
    }

    // MARK: - Bindings
    //
    // Explicit `Binding(get:set:)` rather than key-path projection: the write
    // has to go through `set` to reach the file, and a plain factory makes that
    // obvious at every call site.

    func text(_ key: String, default fallback: String = "") -> Binding<String> {
        Binding(
            get: { self.config.string(key, default: fallback) },
            set: { self.set(key, $0) }
        )
    }

    func flag(_ key: String, default fallback: Bool) -> Binding<Bool> {
        Binding(
            get: { self.config.bool(key, default: fallback) },
            set: { self.set(key, $0 ? "true" : "false") }
        )
    }

    func number(_ key: String, default fallback: Int) -> Binding<Int> {
        Binding(
            get: { self.config.int(key, default: fallback) },
            set: { self.set(key, String($0)) }
        )
    }

    func decimal(_ key: String, default fallback: Double) -> Binding<Double> {
        Binding(
            get: { self.config.double(key, default: fallback) },
            set: { self.set(key, String(format: "%g", $0)) }
        )
    }

    func list(_ key: String) -> [String] { config.list(key) }

    func setList(_ key: String, _ items: [String]) {
        let cleaned = items.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        guard config.lists[key] ?? [] != cleaned else { return }
        config.lists[key] = cleaned
        do {
            try Configuration.writeList(key, cleaned)
            lastError = nil
        } catch {
            lastError = "Could not save \(Configuration.path.path(percentEncoded: false)): "
                + error.localizedDescription
        }
    }

    func folder(_ key: String) -> URL? { config.url(key) }

    func setFolder(_ key: String, _ url: URL?) {
        set(key, url?.path(percentEncoded: false) ?? "")
    }
}

/// Everything the settings window can change, with the key names the pipeline
/// actually reads. Kept in one place so a rename shows up here rather than
/// silently reading back an empty string.
enum ConfigKey {
    static let destination = "destination_directory"
    static let watch = "watch_directory"

    static let provider = "llm_provider"
    static let anthropicKey = "anthropic_api_key"
    static let anthropicModel = "anthropic_model"
    static let openAIKey = "openai_api_key"
    static let openAIModel = "openai_model"
    static let openAIBaseURL = "openai_base_url"

    static let whisperModel = "whisper_model"
    static let whisperLanguage = "whisper_language"
    static let whisperVAD = "whisper_vad"
    static let whisperAutoPrompt = "whisper_auto_prompt"
    static let whisperThreads = "whisper_threads"

    static let diarization = "diarization_enabled"
    static let diarizationThreshold = "diarization_threshold"
    static let splitMeetings = "split_meetings"
    static let splitVideo = "split_video"
    static let meetingGap = "meeting_gap_seconds"
    static let minMeeting = "min_meeting_seconds"
    static let moveSource = "move_source_video"

    static let calendar = "calendar_enabled"
    static let calendarMargin = "calendar_margin_minutes"

    static let requireCamera = "autorecord_require_camera"
    static let useCalendar = "autorecord_use_calendar"
    static let micOnly = "autorecord_mic_only"
    static let startAfter = "autorecord_start_after_seconds"
    static let stopAfter = "autorecord_stop_after_seconds"
    static let minFreeGB = "autorecord_min_free_gb"
    static let obsHost = "obs_host"
    static let obsPort = "obs_port"
    static let obsPassword = "obs_password"

    // slack.py prefers a bot token and channel, falling back to the webhook.
    // Neither bot key is in the CLI's DEFAULT_CONFIG, so the app is the only
    // place they are discoverable.
    static let slackBotToken = "slack_bot_token"
    static let slackChannel = "slack_channel_id"
    static let slackWebhook = "slack_webhook_url"

    static let meetingMode = "meeting_mode"
    static let calendarSource = "calendar_source"
    static let knownParticipants = "known_participants"
    static let whisperPrompt = "whisper_prompt"
    static let diarizationThreads = "diarization_threads"
    static let pollSeconds = "autorecord_poll_seconds"
    static let notesMaxTokens = "notes_max_tokens"
    static let speakerMaxTokens = "speaker_max_tokens"
    static let boundaryMaxTokens = "boundary_max_tokens"

    /// Whisper models the pipeline knows how to fetch, smallest first.
    static let whisperModels = [
        "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo",
    ]
}
