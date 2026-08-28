import SwiftUI

/// The main window: meetings down the left, the selected one on the right.
struct LibraryView: View {
    @State private var library = MeetingLibrary()
    @State private var selection: MeetingFolder?
    @State private var search = ""
    @AppStorage("meetingsFolderPath") private var storedRoot = ""

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 260, ideal: 320)
        } detail: {
            if let selection {
                MeetingDetailView(folder: selection, library: library)
                    // Without this the detail view keeps the previously
                    // selected meeting's @State when the selection changes.
                    .id(selection.id)
            } else {
                ContentUnavailableView(
                    "No meeting selected",
                    systemImage: "waveform",
                    description: Text("Pick a meeting from the list.")
                )
            }
        }
        .searchable(text: $search, placement: .sidebar, prompt: "Search meetings")
        .toolbar {
            ToolbarItem {
                Button {
                    chooseFolder()
                } label: {
                    Label("Choose Folder", systemImage: "folder")
                }
                .help("Pick the folder your meetings are saved to")
            }
            ToolbarItem {
                Button {
                    Task { await library.load(root: resolvedRoot) }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Rescan the meetings folder")
            }
        }
        .task {
            await library.load(root: resolvedRoot)
        }
    }

    // MARK: - Sidebar

    @ViewBuilder
    private var sidebar: some View {
        switch library.phase {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let message):
            ContentUnavailableView {
                Label("Nothing to show", systemImage: "folder.badge.questionmark")
            } description: {
                Text(message)
            } actions: {
                Button("Choose Folder…") { chooseFolder() }
            }
        case .loaded:
            VStack(spacing: 0) {
                List(selection: $selection) {
                    ForEach(groups, id: \.key) { group in
                        Section(group.key) {
                            ForEach(group.value) { folder in
                                MeetingRow(folder: folder).tag(folder)
                            }
                        }
                    }
                }
                .listStyle(.sidebar)

                // The list is drawn from folder names alone; the files behind
                // each one arrive after. On iCloud that second pass is slow
                // enough to be worth saying so.
                if library.enriching {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Reading folders…").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                }
            }
        }
    }

    private var filtered: [MeetingFolder] {
        let query = search.trimmingCharacters(in: .whitespaces)
        guard !query.isEmpty else { return library.folders }
        return library.folders.filter {
            $0.name.localizedCaseInsensitiveContains(query)
        }
    }

    /// Grouped by month, newest first. `folders` is already sorted, so the
    /// groups come out in order without a second sort.
    private var groups: [(key: String, value: [MeetingFolder])] {
        var order: [String] = []
        var buckets: [String: [MeetingFolder]] = [:]
        for folder in filtered {
            let key = folder.date.map {
                $0.formatted(.dateTime.month(.wide).year())
            } ?? "Undated"
            if buckets[key] == nil { order.append(key) }
            buckets[key, default: []].append(folder)
        }
        return order.map { ($0, buckets[$0] ?? []) }
    }

    // MARK: - Folder selection

    private var resolvedRoot: URL? {
        if !storedRoot.isEmpty { return URL(filePath: storedRoot) }
        return Configuration.load().destinationDirectory
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Use Folder"
        panel.message = "Pick the folder your meetings are saved to."
        panel.directoryURL = resolvedRoot
        guard panel.runModal() == .OK, let url = panel.url else { return }
        storedRoot = url.path(percentEncoded: false)
        selection = nil
        Task { await library.load(root: url) }
    }
}

private struct MeetingRow: View {
    let folder: MeetingFolder

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(folder.displayName)
                .lineLimit(2)
            HStack(spacing: 6) {
                if let date = folder.date {
                    Text(date.formatted(date: .abbreviated, time: .shortened))
                }
                // Only once the folder has been listed is this known, so the
                // badge appears with the second pass rather than guessing.
                if folder.contents?.isLegacy == true {
                    Text("transcript only")
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(.quaternary, in: Capsule())
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

#Preview {
    LibraryView()
}
