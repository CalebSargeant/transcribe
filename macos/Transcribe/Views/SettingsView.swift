import SwiftUI

/// Every setting the pipeline reads, editable here.
///
/// There is one meetings folder, not an app one and a CLI one: they were always
/// the same setting, and offering a choice between them only invited them to
/// disagree.
struct SettingsView: View {
    @Environment(Settings.self) private var settings

    var body: some View {
        TabView {
            GeneralSettings().tabItem { Label("General", systemImage: "folder") }
            NotesSettings().tabItem { Label("Notes", systemImage: "text.alignleft") }
            TranscriptionSettings().tabItem { Label("Transcription", systemImage: "waveform") }
            RecordingSettings().tabItem { Label("Recording", systemImage: "record.circle") }
        }
        .frame(width: 540)
        .overlay(alignment: .bottom) {
            if let error = settings.lastError {
                Text(error)
                    .font(.callout)
                    .foregroundStyle(.white)
                    .padding(8)
                    .frame(maxWidth: .infinity)
                    .background(.red)
            }
        }
    }
}

// MARK: - General

private struct GeneralSettings: View {
    @Environment(Settings.self) private var settings

    var body: some View {
        Form {
            Section("Folders") {
                FolderRow(
                    title: "Meetings",
                    help: "Where finished meetings are saved, and what this app lists.",
                    key: ConfigKey.destination
                )
                FolderRow(
                    title: "Watch",
                    help: "New recordings dropped here are transcribed automatically.",
                    key: ConfigKey.watch
                )
            }

            Section("Calendar") {
                Toggle("Match meetings to calendar events", isOn: settings.flag(ConfigKey.calendar, default: true))
                    .help("Gives meetings their real title and the list of who was invited.")
                LabeledContent("Search window") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.calendarMargin, default: 15)) min",
                        value: settings.number(ConfigKey.calendarMargin, default: 15),
                        in: 0...120,
                        step: 5
                    )
                }
                .help("How far either side of a recording to look for an event.")
            }

            Section("Notifications") {
                TextField(
                    "Slack webhook",
                    text: settings.text(ConfigKey.slackWebhook),
                    prompt: Text("https://hooks.slack.com/…")
                )
                Text("Leave empty to skip posting notes to Slack.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section {
                LabeledContent("Config file") {
                    HStack(spacing: 8) {
                        Text(Configuration.path.path(percentEncoded: false))
                            .truncationMode(.head).lineLimit(1)
                        Button("Reveal") {
                            NSWorkspace.shared.activateFileViewerSelecting([Configuration.path])
                        }
                        Button("Reload") { settings.reload() }
                    }
                }
                Text("The command line tool reads these same settings.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}

private struct FolderRow: View {
    @Environment(Settings.self) private var settings
    let title: String
    let help: String
    let key: String

    var body: some View {
        LabeledContent(title) {
            HStack(spacing: 8) {
                Text(settings.folder(key)?.path(percentEncoded: false) ?? "Not set")
                    .truncationMode(.head)
                    .lineLimit(1)
                    .foregroundStyle(settings.folder(key) == nil ? .secondary : .primary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                Button("Choose…") { choose() }
            }
        }
        .help(help)
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Use Folder"
        panel.directoryURL = settings.folder(key)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        settings.setFolder(key, url)
    }
}

// MARK: - Notes

private struct NotesSettings: View {
    @Environment(Settings.self) private var settings

    private var provider: String { settings.config.string(ConfigKey.provider, default: "claude") }

    var body: some View {
        Form {
            Section("Provider") {
                Picker("Generate notes with", selection: settings.text(ConfigKey.provider, default: "claude")) {
                    Text("Claude").tag("claude")
                    Text("OpenAI compatible").tag("openai")
                }
                .pickerStyle(.radioGroup)
            }

            if provider == "claude" {
                Section("Claude") {
                    SecureField("API key", text: settings.text(ConfigKey.anthropicKey), prompt: Text("sk-ant-…"))
                    TextField("Model", text: settings.text(ConfigKey.anthropicModel, default: "claude-haiku-4-5-20251001"))
                }
            } else {
                Section("OpenAI compatible") {
                    SecureField("API key", text: settings.text(ConfigKey.openAIKey), prompt: Text("sk-…"))
                    TextField("Model", text: settings.text(ConfigKey.openAIModel, default: "gpt-4o-mini"))
                    TextField(
                        "Base URL",
                        text: settings.text(ConfigKey.openAIBaseURL),
                        prompt: Text("empty for api.openai.com")
                    )
                    Text("Point at a LiteLLM gateway, Ollama, vLLM or OpenRouter.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }

            Section("Splitting") {
                Toggle("Split a recording into separate meetings", isOn: settings.flag(ConfigKey.splitMeetings, default: true))
                Toggle("Also cut the video into one clip per meeting", isOn: settings.flag(ConfigKey.splitVideo, default: true))
                    .disabled(!settings.config.bool(ConfigKey.splitMeetings, default: true))
                LabeledContent("Silence between meetings") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.meetingGap, default: 180))s",
                        value: settings.number(ConfigKey.meetingGap, default: 180),
                        in: 30...1800, step: 30
                    )
                }
                LabeledContent("Shortest meeting") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.minMeeting, default: 120))s",
                        value: settings.number(ConfigKey.minMeeting, default: 120),
                        in: 30...1800, step: 30
                    )
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Transcription

private struct TranscriptionSettings: View {
    @Environment(Settings.self) private var settings

    var body: some View {
        Form {
            Section("Whisper") {
                Picker("Model", selection: settings.text(ConfigKey.whisperModel, default: "large-v3-turbo")) {
                    ForEach(ConfigKey.whisperModels, id: \.self) { Text($0).tag($0) }
                }
                .help("Downloaded on first use. large-v3-turbo is the accuracy/speed sweet spot on Apple Silicon.")

                TextField("Language", text: settings.text(ConfigKey.whisperLanguage, default: "en"))
                    .help("An ISO code such as en or nl. Set 'auto' to detect.")

                LabeledContent("Threads") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.whisperThreads, default: 8))",
                        value: settings.number(ConfigKey.whisperThreads, default: 8),
                        in: 1...32
                    )
                }

                Toggle("Voice activity detection", isOn: settings.flag(ConfigKey.whisperVAD, default: true))
                Text("Leave on. Without it Whisper invents filler over room tone and can lock into a repetition loop.")
                    .font(.caption).foregroundStyle(.secondary)

                Toggle("Learn vocabulary from past meetings", isOn: settings.flag(ConfigKey.whisperAutoPrompt, default: true))
                Text("Builds the decoder prompt from your calendar, past notes and corrections, instead of a hand-kept list.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("Speakers") {
                Toggle("Separate speakers", isOn: settings.flag(ConfigKey.diarization, default: true))
                LabeledContent("Merge voices at") {
                    Slider(
                        value: settings.decimal(ConfigKey.diarizationThreshold, default: 0.8),
                        in: 0.3...0.95, step: 0.05
                    ) {
                        Text("Threshold")
                    } minimumValueLabel: {
                        Text("more").font(.caption)
                    } maximumValueLabel: {
                        Text("fewer").font(.caption)
                    }
                }
                .disabled(!settings.config.bool(ConfigKey.diarization, default: true))
                Text(
                    String(
                        format: "%.2f — higher merges more voices together. Below about 0.8 a long meeting splits one person into several.",
                        settings.config.double(ConfigKey.diarizationThreshold, default: 0.8)
                    )
                )
                .font(.caption).foregroundStyle(.secondary)
            }

            Section("Source files") {
                Toggle("Move the recording into the meeting folder", isOn: settings.flag(ConfigKey.moveSource, default: true))
                Text("Off leaves the original where it was recorded and copies nothing.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Recording

private struct RecordingSettings: View {
    @Environment(Settings.self) private var settings

    var body: some View {
        Form {
            Section("When to record") {
                Toggle("Require the camera to be on", isOn: settings.flag(ConfigKey.requireCamera, default: true))
                Toggle("Accept a calendar event as the signal", isOn: settings.flag(ConfigKey.useCalendar, default: true))
                Toggle("Microphone alone is enough", isOn: settings.flag(ConfigKey.micOnly, default: false))
                Text("The microphone alone also fires on dictation, voice notes and Siri, which is why it needs a second signal by default.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("Timing") {
                LabeledContent("Start after") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.startAfter, default: 45))s",
                        value: settings.number(ConfigKey.startAfter, default: 45),
                        in: 5...600, step: 5
                    )
                }
                .help("Long enough that a notification chime does not produce a file.")
                LabeledContent("Stop after") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.stopAfter, default: 120))s",
                        value: settings.number(ConfigKey.stopAfter, default: 120),
                        in: 10...900, step: 10
                    )
                }
                .help("Long enough that swapping a headset does not chop a meeting in two.")
                LabeledContent("Need free space") {
                    Stepper(
                        "\(settings.config.int(ConfigKey.minFreeGB, default: 10)) GB",
                        value: settings.number(ConfigKey.minFreeGB, default: 10),
                        in: 1...500, step: 1
                    )
                }
                .help("A truncated recording on a full disk loses the meeting entirely.")
            }

            Section("OBS") {
                TextField("Host", text: settings.text(ConfigKey.obsHost, default: "localhost"))
                LabeledContent("Port") {
                    TextField(
                        "Port",
                        value: settings.number(ConfigKey.obsPort, default: 4455),
                        format: .number.grouping(.never)
                    )
                    .labelsHidden()
                    .frame(width: 90)
                }
                SecureField("Password", text: settings.text(ConfigKey.obsPassword))
                Text("Enable OBS ▸ Tools ▸ WebSocket Server Settings first.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}

#Preview {
    SettingsView()
        .environment(Settings(config: Configuration(values: [:])))
}
