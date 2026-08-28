import SwiftUI

/// The transcript, one row per segment, with the speaker and a timestamp that
/// seeks the recording.
struct TranscriptPane: View {
    let record: MeetingRecord?
    let legacyTranscript: String?
    let onSeek: (Double) -> Void

    @State private var filter = ""
    @State private var speakerFilter: String?

    var body: some View {
        VStack(spacing: 0) {
            if record != nil {
                controls
                Divider()
            }
            transcript
        }
    }

    @ViewBuilder
    private var controls: some View {
        HStack {
            TextField("Filter lines", text: $filter)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)

            if let speakers = record?.speakingParticipants, speakers.count > 1 {
                Picker("Speaker", selection: $speakerFilter) {
                    Text("All speakers").tag(String?.none)
                    ForEach(speakers, id: \.self) { Text($0).tag(String?.some($0)) }
                }
                .frame(maxWidth: 220)
            }

            Spacer()

            if let count = visibleSegments?.count {
                Text("\(count) line\(count == 1 ? "" : "s")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    private var visibleSegments: [MeetingRecord.Segment]? {
        guard let segments = record?.segments else { return nil }
        let query = filter.trimmingCharacters(in: .whitespaces)
        return segments.filter { segment in
            if let speakerFilter, segment.speaker != speakerFilter { return false }
            if !query.isEmpty, !segment.text.localizedCaseInsensitiveContains(query) {
                return false
            }
            return true
        }
    }

    @ViewBuilder
    private var transcript: some View {
        if let segments = visibleSegments {
            if segments.isEmpty {
                ContentUnavailableView.search
            } else {
                List(segments) { segment in
                    SegmentRow(segment: segment, onSeek: onSeek)
                        .listRowSeparator(.hidden)
                }
                .listStyle(.inset)
            }
        } else if let legacyTranscript, !legacyTranscript.isEmpty {
            // Older folders hold one unstructured blob with no timings, so
            // there is nothing to seek to and nothing to attribute.
            ScrollView {
                Text(legacyTranscript)
                    .textSelection(.enabled)
                    .frame(maxWidth: 780, alignment: .leading)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .padding(24)
            }
        } else {
            ContentUnavailableView(
                "No transcript",
                systemImage: "text.alignleft",
                description: Text("This folder has no transcript file.")
            )
        }
    }
}

private struct SegmentRow: View {
    let segment: MeetingRecord.Segment
    let onSeek: (Double) -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Button(segment.timestamp) {
                onSeek(segment.start)
            }
            .buttonStyle(.link)
            .font(.caption.monospacedDigit())
            .frame(width: 64, alignment: .leading)

            VStack(alignment: .leading, spacing: 2) {
                if let speaker = segment.speaker {
                    Text(speaker)
                        .font(.caption)
                        .foregroundStyle(Color(for: speaker))
                }
                Text(segment.text)
                    .textSelection(.enabled)
            }
        }
        .padding(.vertical, 3)
    }
}

private extension Color {
    /// A stable colour per speaker so the same voice reads the same way down
    /// the page. Hashing the name keeps it stable across reloads, which
    /// indexing into the speaker list would not once a filter reorders it.
    init(for speaker: String) {
        let palette: [Color] = [.blue, .purple, .teal, .orange, .pink, .indigo, .green, .brown]
        var hash: UInt64 = 5381
        for byte in speaker.utf8 { hash = hash &* 33 &+ UInt64(byte) }
        self = palette[Int(hash % UInt64(palette.count))]
    }
}
