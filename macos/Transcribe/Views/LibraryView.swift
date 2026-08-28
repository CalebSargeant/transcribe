import SwiftUI

/// The main window: meetings down the left, the selected one on the right.
struct LibraryView: View {
    @Environment(Settings.self) private var settings
    @Environment(TagIndex.self) private var tags
    @State private var library = MeetingLibrary()
    @State private var selection: MeetingFolder?
    @State private var search = ""
    @State private var tagFilter: String?

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
                Menu {
                    Button("All meetings") { tagFilter = nil }
                    if !tags.allTags.isEmpty {
                        Divider()
                        ForEach(tags.allTags, id: \.self) { tag in
                            Button {
                                tagFilter = tag
                            } label: {
                                if tagFilter == tag {
                                    Label(tag, systemImage: "checkmark")
                                } else {
                                    Text(tag)
                                }
                            }
                        }
                    }
                } label: {
                    Label(
                        tagFilter ?? "All categories",
                        systemImage: tagFilter == nil ? "tag" : "tag.fill"
                    )
                }
                .help("Show only meetings in one category")
            }
            ToolbarItem {
                Button {
                    chooseFolder()
                } label: {
                    Label("Change Meetings Folder", systemImage: "folder.badge.gearshape")
                }
                .help("Change which folder this app lists meetings from")
            }
            ToolbarItem {
                Button {
                    Task {
                        await library.load(root: settings.folder(ConfigKey.destination))
                        await tags.load(folders: library.folders)
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Rescan the meetings folder for new or changed meetings")
            }
        }
        .task(id: settings.folder(ConfigKey.destination)) {
            // Reloads on its own when the folder is changed in Settings.
            await library.load(root: settings.folder(ConfigKey.destination))
            await tags.load(folders: library.folders)
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
        case .needsAccess(let url):
            // Choosing the folder in an open panel is what grants access, so
            // the button is the fix rather than a retry.
            ContentUnavailableView {
                Label("Cannot read that folder", systemImage: "lock")
            } description: {
                Text(
                    "\(url.path(percentEncoded: false))\n\nmacOS is blocking this app from "
                    + "reading it. Choosing the folder below grants access. Granting Transcribe "
                    + "Full Disk Access in System Settings > Privacy & Security also works."
                )
            } actions: {
                Button("Choose Folder…") { chooseFolder() }
                Button("Open Privacy Settings") {
                    if let settings = URL(
                        string:
                            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
                    ) {
                        NSWorkspace.shared.open(settings)
                    }
                }
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
        return library.folders.filter { folder in
            if let tagFilter,
                !tags.tags(for: folder.id).contains(where: {
                    $0.caseInsensitiveCompare(tagFilter) == .orderedSame
                })
            { return false }
            if !query.isEmpty, !folder.name.localizedCaseInsensitiveContains(query) {
                return false
            }
            return true
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

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Use Folder"
        panel.message = "Pick the folder your meetings are saved to."
        panel.directoryURL = settings.folder(ConfigKey.destination)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        selection = nil
        // Writing it through is what makes .task(id:) reload, and what the CLI
        // will read on its next run.
        settings.setFolder(ConfigKey.destination, url)
    }
}

private struct MeetingRow: View {
    @Environment(TagIndex.self) private var tags
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
                        .help(
                            "Saved before this pipeline wrote structured notes. "
                                + "The transcript and summary are here; speakers, timestamps "
                                + "and notes are not. Generate Notes rebuilds them."
                        )
                }
                ForEach(tags.tags(for: folder.id).prefix(2), id: \.self) { tag in
                    Text(tag)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(.tint.opacity(0.15), in: Capsule())
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
        .environment(Settings(config: Configuration(values: [:])))
        .environment(TagIndex())
        .environment(Pipeline())
}
