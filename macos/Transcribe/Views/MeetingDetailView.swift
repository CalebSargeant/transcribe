import SwiftUI

/// One meeting: its notes, its transcript, and the recording they came from.
struct MeetingDetailView: View {
    let folder: MeetingFolder
    let library: MeetingLibrary
    /// A point in the recording to jump to once it is ready, set when the
    /// meeting was opened from a search result.
    var seekOnOpen: Double?

    @Environment(TagIndex.self) private var tags
    @Environment(Pipeline.self) private var pipeline
    @State private var contents: MeetingFolder.Contents?
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
            if contents?.media != nil {
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
                    Label("Show in Finder", systemImage: "arrow.up.forward.app")
                }
                .help("Open this meeting's folder in Finder")
            }
            ToolbarItem {
                Button {
                    pipeline.regenerate(
                        folder: folder,
                        media: contents?.media,
                        label: record == nil ? "Generating notes" : "Regenerating notes"
                    )
                } label: {
                    Label(
                        record == nil ? "Generate Notes" : "Regenerate Notes",
                        systemImage: "sparkles"
                    )
                }
                .disabled(contents?.media == nil || pipeline.isRunning)
                .help(
                    contents?.media == nil
                        ? "There is no recording in this folder to process"
                        : "Run the pipeline over this recording again"
                )
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
            if showPlayer, contents?.media != nil {
                PlayerPane(playback: playback, media: contents?.media)
                    .frame(minHeight: 200, idealHeight: 320)
            }

            VStack(spacing: 0) {
                TagBar(folder: folder)
                if pipeline.state != .idle {
                    PipelineStatusBar()
                }
                Divider()

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
            meetingStart: record?.clipOffset(forMedia: contents?.media) ?? 0
        )
    }

    private func load() async {
        loading = true
        defer { loading = false }

        // The background pass may not have reached this folder yet, so listing
        // it here is what keeps selection responsive.
        let contents = await library.contents(of: folder)
        self.contents = contents

        do {
            record = try await MeetingLibrary.loadRecord(contents.notesJSON)
        } catch {
            // A folder whose JSON will not parse still has its text files, so
            // the error is reported without giving up on the meeting.
            loadError = "notes.json could not be read: \(error.localizedDescription)"
        }

        if record == nil {
            legacyTranscript = await MeetingLibrary.loadText(contents.transcriptText)
            legacySummary = await MeetingLibrary.loadText(contents.summaryText)
        }

        await playback.open(contents.media)

        // Only now is there a player to seek.
        if let seekOnOpen {
            tab = .transcript
            seek(to: seekOnOpen)
        }
    }
}

/// The recording itself, or an explanation of why it will not play.
private struct PlayerPane: View {
    let playback: PlaybackController
    let media: URL?

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
                if let media {
                    Button("Open in QuickTime") { NSWorkspace.shared.open(media) }
                    Button("Reveal in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([media])
                    }
                }
            }
        }
    }
}


/// The meeting's categories, editable inline.
private struct TagBar: View {
    @Environment(TagIndex.self) private var tags
    let folder: MeetingFolder

    @State private var draft = ""
    @State private var adding = false
    @State private var error: String?

    private var current: [String] { tags.tags(for: folder.id) }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "tag")
                .foregroundStyle(.secondary)
                .help("Categories for this meeting")

            ForEach(current, id: \.self) { tag in
                HStack(spacing: 4) {
                    Text(tag)
                    Button {
                        apply { try tags.toggle(tag, for: folder.id) }
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Remove \(tag)")
                }
                .font(.caption)
                .padding(.horizontal, 7)
                .padding(.vertical, 2)
                .background(.tint.opacity(0.15), in: Capsule())
            }

            if adding {
                TextField("Category", text: $draft)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                    .onSubmit(commit)
                Button("Add", action: commit).disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Cancel") { adding = false; draft = "" }
            } else {
                Menu {
                    Button("New category…") { adding = true }
                    // Offer what is already in use, so the same category is not
                    // retyped three different ways.
                    let unused = tags.allTags.filter { existing in
                        !current.contains { $0.caseInsensitiveCompare(existing) == .orderedSame }
                    }
                    if !unused.isEmpty {
                        Divider()
                        ForEach(unused, id: \.self) { tag in
                            Button(tag) { apply { try tags.toggle(tag, for: folder.id) } }
                        }
                    }
                } label: {
                    Label("Add", systemImage: "plus.circle")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Categorise this meeting")
            }

            Spacer()

            if let error {
                Text(error).font(.caption).foregroundStyle(.red).lineLimit(1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func commit() {
        let value = draft.trimmingCharacters(in: .whitespaces)
        guard !value.isEmpty else { return }
        apply { try tags.set(current + [value], for: folder.id) }
        draft = ""
        adding = false
    }

    private func apply(_ change: () throws -> Void) {
        do {
            try change()
            error = nil
        } catch {
            self.error = "Could not save categories"
        }
    }
}
