import SwiftUI

/// One meeting: its notes, its transcript, and the recording they came from.
struct MeetingDetailView: View {
    let folder: MeetingFolder

    @State private var record: MeetingRecord?
    @State private var legacyTranscript: String?
    @State private var legacySummary: String?
    @State private var loadError: String?
    @State private var loading = true
    @State private var tab: Tab = .notes
    @State private var playback = PlaybackController()
    @State private var showPlayer = true

    private enum Tab: String, CaseIterable, Identifiable {
        case notes = "Notes"
        case transcript = "Transcript"
        var id: String { rawValue }
    }

    var body: some View {
        Group {
            if loading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                content
            }
        }
        .navigationTitle(record?.displayTitle ?? folder.displayName)
        .navigationSubtitle(subtitle)
        .toolbar {
            if folder.media != nil {
                ToolbarItem {
                    Toggle(isOn: $showPlayer) {
                        Label("Player", systemImage: "play.rectangle")
                    }
                    .help("Show the recording")
                }
            }
            ToolbarItem {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([folder.id])
                } label: {
                    Label("Reveal in Finder", systemImage: "folder")
                }
                .help("Reveal this meeting's folder in Finder")
            }
        }
        .task {
            await load()
        }
    }

    private var subtitle: String {
        var parts: [String] = []
        if let date = folder.date {
            parts.append(date.formatted(date: .abbreviated, time: .shortened))
        }
        if let seconds = record?.durationSeconds, seconds > 0 {
            parts.append("\(Int(seconds / 60)) min")
        }
        let people = record?.speakingParticipants.count ?? 0
        if people > 0 { parts.append("\(people) voice\(people == 1 ? "" : "s")") }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder
    private var content: some View {
        VSplitView {
            if showPlayer, folder.media != nil {
                PlayerPane(playback: playback, folder: folder)
                    .frame(minHeight: 200, idealHeight: 320)
            }

            VStack(spacing: 0) {
                Picker("View", selection: $tab) {
                    ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding(.horizontal)
                .padding(.vertical, 8)

                Divider()

                switch tab {
                case .notes:
                    NotesPane(
                        record: record,
                        legacySummary: legacySummary,
                        loadError: loadError,
                        onSeek: seek
                    )
                case .transcript:
                    TranscriptPane(
                        record: record,
                        legacyTranscript: legacyTranscript,
                        onSeek: seek
                    )
                }
            }
            .frame(minHeight: 240)
        }
    }

    private func seek(to second: Double) {
        guard playback.phase == .ready else { return }
        showPlayer = true
        playback.seek(
            toRecordingSecond: second,
            meetingStart: record?.clipOffset(forMedia: folder.media) ?? 0
        )
    }

    private func load() async {
        loading = true
        defer { loading = false }

        do {
            record = try await MeetingLibrary.loadRecord(folder)
        } catch {
            // A folder whose JSON will not parse still has its text files, so
            // the error is reported without giving up on the meeting.
            loadError = "notes.json could not be read: \(error.localizedDescription)"
        }

        if record == nil {
            legacyTranscript = await MeetingLibrary.loadText(folder.transcriptText)
            legacySummary = await MeetingLibrary.loadText(folder.summaryText)
        }

        await playback.open(folder.media)
    }
}

/// The recording itself, or an explanation of why it will not play.
private struct PlayerPane: View {
    let playback: PlaybackController
    let folder: MeetingFolder

    var body: some View {
        switch playback.phase {
        case .none:
            Color.clear
        case .checking:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .ready:
            if let player = playback.player {
                VideoPlayerView(player: player)
            }
        case .unplayable(let reason):
            ContentUnavailableView {
                Label("Cannot play this recording", systemImage: "film.stack")
            } description: {
                Text(reason)
            } actions: {
                if let media = folder.media {
                    Button("Open in QuickTime") { NSWorkspace.shared.open(media) }
                    Button("Reveal in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([media])
                    }
                }
            }
        }
    }
}
