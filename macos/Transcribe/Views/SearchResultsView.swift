import SwiftUI

/// Search results across every transcript, not just the titles.
///
/// A library of a hundred meetings is only worth keeping if you can ask it what
/// was said. Matching folder names answers almost nothing, because the thing
/// you remember is a phrase from the conversation.
struct SearchResultsView: View {
    @Environment(MeetingIndex.self) private var index
    let query: String
    let onOpen: (URL, Double?) -> Void

    /// Computed once per query change, not once per `body`. `results` was read
    /// three times per render and each read walked every meeting's haystack.
    @State private var results: [IndexedMeeting] = []

    var body: some View {
        Group {
            if results.isEmpty {
                ContentUnavailableView {
                    Label("No matches", systemImage: "magnifyingglass")
                } description: {
                    Text(
                        index.building
                            ? "Still reading the library — \(Int(index.progress * 100))% indexed."
                            : "Nothing in your meetings mentions “\(query)”."
                    )
                }
            } else {
                List {
                    ForEach(results) { meeting in
                        Section {
                            let matches = meeting.matches(query)
                            if matches.isEmpty {
                                // The match was in the title, notes or attendees.
                                Button {
                                    onOpen(meeting.folder, nil)
                                } label: {
                                    Text("Matched outside the transcript")
                                        .font(.callout).foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            ForEach(matches, id: \.self) { line in
                                Button {
                                    onOpen(meeting.folder, meeting.isLegacy ? nil : line.seconds)
                                } label: {
                                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                                        if !line.timestamp.isEmpty {
                                            Text(line.timestamp)
                                                .font(.caption.monospacedDigit())
                                                .foregroundStyle(.secondary)
                                                .frame(width: 62, alignment: .leading)
                                        }
                                        VStack(alignment: .leading, spacing: 2) {
                                            if let speaker = line.speaker {
                                                Text(speaker).font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                            highlighted(line.text)
                                        }
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        } header: {
                            HStack {
                                Text(meeting.title)
                                if let date = meeting.date {
                                    Text(date.formatted(date: .abbreviated, time: .shortened))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Open") { onOpen(meeting.folder, nil) }
                                    .buttonStyle(.link)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .task(id: query) { results = index.search(query) }
        .navigationTitle("“\(query)”")
        .navigationSubtitle(
            results.isEmpty ? "" : "\(results.count) meeting\(results.count == 1 ? "" : "s")")
    }

    /// Bold the matched span so the eye lands on it.
    private func highlighted(_ text: String) -> Text {
        guard let range = text.range(of: query, options: .caseInsensitive) else {
            return Text(text)
        }
        return Text(text[text.startIndex..<range.lowerBound])
            + Text(text[range]).bold().foregroundColor(.accentColor)
            + Text(text[range.upperBound...])
    }
}
