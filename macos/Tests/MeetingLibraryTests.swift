import Foundation
import Testing

@testable import Transcribe

// Pure logic only: folder naming, the config format, timecodes, and decoding.
// Nothing here touches the view layer or the real library.

@Suite("Folder names")
struct FolderNameTests {
    @Test("this pipeline's current naming")
    func currentScheme() throws {
        let date = try #require(
            MeetingLibrary.folderDate(from: "2026-08-27 1105 Branching and release strategy"))
        let parts = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        #expect(parts.year == 2026 && parts.month == 8 && parts.day == 27)
        #expect(parts.hour == 11 && parts.minute == 5)
    }

    @Test("the pipeline's older naming")
    func olderScheme() throws {
        let date = try #require(
            MeetingLibrary.folderDate(from: "2024-10-30 11-04-23 Align Linux Servers"))
        let parts = Calendar.current.dateComponents([.hour, .minute, .second], from: date)
        #expect(parts.hour == 11 && parts.minute == 4 && parts.second == 23)
    }

    /// Three quarters of an existing library is named by Teams, not by this
    /// pipeline, and its date sits in the middle of the name rather than at the
    /// front. Missing it left those folders undated and sorted to the bottom.
    @Test("Teams recordings carry the stamp in the middle")
    func teamsScheme() throws {
        let date = try #require(
            MeetingLibrary.folderDate(from: "Standup-20241120_095537-Meeting Recording"))
        let parts = Calendar.current.dateComponents([.year, .month, .day, .hour], from: date)
        #expect(parts.year == 2024 && parts.month == 11 && parts.day == 20 && parts.hour == 9)
    }

    @Test("a name with no date at all")
    func noDate() {
        #expect(MeetingLibrary.folderDate(from: "Some folder") == nil)
    }

    @Test(
        "the timestamp is stripped for display",
        arguments: [
            ("2026-08-27 1105 Branching strategy", "Branching strategy"),
            ("2024-10-30 11-04-23 Align Linux Servers", "Align Linux Servers"),
            ("Standup-20241120_095537-Meeting Recording", "Standup"),
            ("Refinement-20240724_131816-Meeting Recording", "Refinement"),
            ("No date here", "No date here"),
        ])
    func displayName(raw: String, expected: String) {
        let folder = MeetingFolder(id: URL(filePath: "/tmp/\(raw)"), name: raw, date: nil)
        #expect(folder.displayName == expected)
    }

    /// A folder whose name is nothing but a timestamp must not render blank.
    @Test("a name that is only a date keeps something to show")
    func dateOnlyName() {
        let folder = MeetingFolder(id: URL(filePath: "/tmp/x"), name: "2026-08-27 1105", date: nil)
        #expect(folder.displayName == "2026-08-27 1105")
    }
}

@Suite("Configuration")
struct ConfigurationTests {
    /// A long path gets wrapped by the YAML writer and folded back on read.
    /// Taking only the first line produced a path that existed nowhere and
    /// looked entirely plausible.
    @Test("a folded value is rejoined")
    func foldedValue() {
        let yaml = """
            destination_directory: /Users/x/Library/Mobile Documents/60-69
              Work & Career/62 Files/Meetings
            watch_directory: /Users/x/Movies
            """
        let values = Configuration.scalars(in: yaml)
        #expect(
            values["destination_directory"]
                == "/Users/x/Library/Mobile Documents/60-69 Work & Career/62 Files/Meetings")
        #expect(values["watch_directory"] == "/Users/x/Movies")
    }

    @Test("nested keys and list items are not swallowed as continuations")
    func nestedStructure() {
        let yaml = """
            top: value
            nested:
              child: 1
            listy:
              - one
              - two
            after: last
            """
        let values = Configuration.scalars(in: yaml)
        #expect(values["top"] == "value")
        #expect(values["after"] == "last")
        #expect(values["nested"] == nil)
        #expect(values["listy"] == nil)
    }

    @Test("comments and quotes")
    func commentsAndQuotes() {
        let yaml = """
            # a leading comment
            provider: openai  # trailing
            quoted: "spaced value"
            empty:
            """
        let values = Configuration.scalars(in: yaml)
        #expect(values["provider"] == "openai")
        #expect(values["quoted"] == "spaced value")
        #expect(values["empty"] == nil)
    }

    /// A '#' inside a path is part of the path, not the start of a comment.
    @Test("a hash without leading whitespace stays in the value")
    func hashInValue() {
        #expect(Configuration.scalars(in: "path: /tmp/a#b/c")["path"] == "/tmp/a#b/c")
    }

    @Test("a missing file yields empty settings, not a crash")
    func missingFile() {
        let config = Configuration.load(from: URL(filePath: "/nonexistent/config.yaml"))
        #expect(config.destinationDirectory == nil)
    }
}

@Suite("Timecodes")
struct TimecodeTests {
    @Test(
        arguments: [
            ("00:00:00", 0.0), ("00:00:02", 2.0), ("01:02:03", 3723.0), ("12:34", 754.0),
        ])
    func parsing(text: String, expected: Double) {
        #expect(Timecode.seconds(from: text) == expected)
    }

    @Test(arguments: ["", "nonsense", "1:2:3:4"])
    func rejected(text: String) {
        #expect(Timecode.seconds(from: text) == nil)
    }

    @Test("round trip")
    func roundTrip() throws {
        let seconds = try #require(Timecode.seconds(from: "02:21:51"))
        #expect(Timecode.text(from: seconds) == "02:21:51")
    }
}

@Suite("Decoding notes.json")
struct DecodingTests {
    /// The pipeline writes local wall-clock time with no offset, which the
    /// `.iso8601` strategy rejects outright.
    @Test("dates have no timezone")
    func dateWithoutZone() throws {
        let json = #"{"index":1,"start":0,"end":1,"duration_seconds":1,"attendees":[],"speakers":[],"segments":[],"recording_started_at":"2026-08-27T11:05:56"}"#
        let record = try PipelineDate.decoder().decode(
            MeetingRecord.self, from: Data(json.utf8))
        let date = try #require(record.recordingStartedAt)
        let parts = Calendar.current.dateComponents([.hour, .minute, .second], from: date)
        #expect(parts.hour == 11 && parts.minute == 5 && parts.second == 56)
    }

    @Test("a segment with no attributed speaker")
    func nullSpeaker() throws {
        let json = #"{"index":1,"start":0,"end":1,"duration_seconds":1,"attendees":[],"speakers":["Speaker 1"],"segments":[{"start":0,"end":1,"timestamp":"00:00:00","text":"hi","speaker":null},{"start":1,"end":2,"timestamp":"00:00:01","text":"yes","speaker":"Speaker 1"}]}"#
        let record = try PipelineDate.decoder().decode(
            MeetingRecord.self, from: Data(json.utf8))
        #expect(record.segments.count == 2)
        #expect(record.speakingParticipants == ["Speaker 1"])
    }

    @Test("absent note arrays decode as empty, not as a failure")
    func sparseNotes() throws {
        let json = #"{"index":1,"start":0,"end":1,"duration_seconds":1,"attendees":[],"speakers":[],"segments":[],"notes":{"title":"T","summary":"S"}}"#
        let record = try PipelineDate.decoder().decode(
            MeetingRecord.self, from: Data(json.utf8))
        let notes = try #require(record.notes)
        #expect(notes.decisions.isEmpty && notes.nextSteps.isEmpty && notes.details.isEmpty)
        #expect(record.displayTitle == "T")
    }

    @Test("an unrecognised decision status does not fail the file")
    func unknownStatus() throws {
        let json = #"{"index":1,"start":0,"end":1,"duration_seconds":1,"attendees":[],"speakers":[],"segments":[],"notes":{"decisions":[{"title":"a","detail":"b","status":"brand_new_value"}]}}"#
        let record = try PipelineDate.decoder().decode(
            MeetingRecord.self, from: Data(json.utf8))
        #expect(record.notes?.decisions.first?.status == .needsFurtherDiscussion)
    }

    @Test("'Unassigned' is an absent owner, not a person")
    func unassignedOwner() {
        let owned = MeetingRecord.NextStep(owner: "Arno", title: "t", detail: "d")
        let unowned = MeetingRecord.NextStep(owner: "Unassigned", title: "t", detail: "d")
        let blank = MeetingRecord.NextStep(owner: "  ", title: "t", detail: "d")
        #expect(owned.assignedOwner == "Arno")
        #expect(unowned.assignedOwner == nil)
        #expect(blank.assignedOwner == nil)
    }
}

@Suite("Seeking")
struct SeekTests {
    private func record(start: Double, source: String) throws -> MeetingRecord {
        let json = """
            {"index":1,"start":\(start),"end":9999,"duration_seconds":100,"attendees":[],
             "speakers":[],"segments":[],"source_file":"\(source)"}
            """
        return try PipelineDate.decoder().decode(MeetingRecord.self, from: Data(json.utf8))
    }

    /// A recording holding one meeting is moved in whole, so its timestamps
    /// already line up and must not be shifted.
    @Test("the whole recording is not offset")
    func wholeRecording() throws {
        let meeting = try record(start: 2.37, source: "/Movies/2026-08-27 110555.qta")
        let media = URL(filePath: "/Meetings/x/2026-08-27 110555.qta")
        #expect(meeting.clipOffset(forMedia: media) == 0)
    }

    /// A recording split across meetings is cut, and the clip starts partway
    /// through, so the meeting's own start has to come off.
    @Test("a cut clip is offset by the meeting start")
    func cutClip() throws {
        let meeting = try record(start: 8511.65, source: "/Movies/2026-08-25 093417.mov")
        let media = URL(filePath: "/Meetings/x/2026-08-25 1156 Janeway hosting.mov")
        #expect(meeting.clipOffset(forMedia: media) == 8511.65)
    }

    @Test("no media at all falls back to the meeting start")
    func noMedia() throws {
        let meeting = try record(start: 12, source: "/Movies/a.mov")
        #expect(meeting.clipOffset(forMedia: nil) == 12)
    }
}

@Suite("Scanning")
struct ScanTests {
    private func makeLibrary(_ build: (URL) throws -> Void) throws -> ([MeetingFolder], URL) {
        let root = URL(filePath: NSTemporaryDirectory())
            .appending(path: "transcribe-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try build(root)
        return (MeetingLibrary.scan(root: root), root)
    }

    private func folder(_ root: URL, _ name: String, files: [String]) throws {
        let directory = root.appending(path: name)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for file in files {
            try Data("x".utf8).write(to: directory.appending(path: file))
        }
    }

    /// The first pass draws the sidebar from folder names alone. Listing every
    /// folder up front cost 13 seconds of wall clock on an iCloud library, all
    /// of it before anything appeared on screen.
    @Test("the first pass does no per-folder IO")
    func scanIsNameOnly() throws {
        let (folders, root) = try makeLibrary { root in
            try folder(root, "2026-01-01 0900 Real", files: ["transcript.txt"])
        }
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(folders.count == 1)
        #expect(folders[0].displayName == "Real")
        #expect(folders[0].date != nil)
        #expect(folders[0].contents == nil)
    }

    @Test("newest first, undated last")
    func ordering() throws {
        let (folders, root) = try makeLibrary { root in
            try folder(root, "2026-01-01 0900 Older", files: ["transcript.txt"])
            try folder(root, "2026-06-01 0900 Newer", files: ["transcript.txt"])
            try folder(root, "Undated", files: ["transcript.txt"])
        }
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(folders.map(\.displayName) == ["Newer", "Older", "Undated"])
    }

    @Test("a missing root yields nothing rather than throwing")
    func missingRoot() {
        #expect(MeetingLibrary.scan(root: URL(filePath: "/nonexistent/meetings")).isEmpty)
    }

    @Test("a folder with neither notes nor a transcript is not a meeting")
    func requiresContent() throws {
        let (_, root) = try makeLibrary { root in
            try folder(root, "Real", files: ["transcript.txt"])
            try folder(root, "Empty", files: ["random.pdf"])
        }
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(MeetingLibrary.listContents(of: root.appending(path: "Real")).isMeeting)
        #expect(!MeetingLibrary.listContents(of: root.appending(path: "Empty")).isMeeting)
    }

    /// Older folders carry only `<name>_transcription.txt`, and they are the
    /// bulk of an existing library.
    @Test("legacy folders are found and marked")
    func legacyLayout() throws {
        let (_, root) = try makeLibrary { root in
            try folder(
                root, "2024-10-30 11-04-23 Old",
                files: ["2024-10-30 11-04-23 Old_transcription.txt", "x_summary.txt"])
        }
        defer { try? FileManager.default.removeItem(at: root) }
        let contents = MeetingLibrary.listContents(of: root.appending(path: "2024-10-30 11-04-23 Old"))
        #expect(contents.isMeeting)
        #expect(contents.isLegacy)
        #expect(contents.transcriptText != nil)
        #expect(contents.summaryText != nil)
    }

    /// Extracted audio sits beside the video; the video is what to play.
    @Test("video wins over the wav beside it")
    func prefersVideo() throws {
        let (_, root) = try makeLibrary { root in
            try folder(root, "A", files: ["transcript.txt", "a.wav", "a.mov"])
        }
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(MeetingLibrary.listContents(of: root.appending(path: "A")).media?.pathExtension == "mov")
    }

    @Test("listing a folder that is not there is empty, not a crash")
    func missingFolder() {
        #expect(!MeetingLibrary.listContents(of: URL(filePath: "/nonexistent/x")).isMeeting)
    }
}

@Suite("Writing config.yaml")
struct ConfigWriteTests {
    /// The CLI's own save_config round-trips through yaml.dump and loses every
    /// comment in the file. Editing the line in place keeps them.
    @Test("comments and untouched keys survive an edit")
    func preservesEverythingElse() {
        let original = """
            # Where recordings are watched for
            watch_directory: /Users/x/Movies

            # The provider used for notes
            llm_provider: claude
            anthropic_model: claude-haiku-4-5-20251001
            """
        let updated = Configuration.apply(["llm_provider": "openai"], to: original)
        #expect(updated.contains("# Where recordings are watched for"))
        #expect(updated.contains("# The provider used for notes"))
        #expect(updated.contains("watch_directory: /Users/x/Movies"))
        #expect(updated.contains("llm_provider: openai"))
        #expect(!updated.contains("llm_provider: claude"))
        #expect(updated.contains("anthropic_model: claude-haiku-4-5-20251001"))
    }

    /// The wrapped value spans two lines. Replacing only the first would leave
    /// the tail behind as a stray line that reparses as part of the new value.
    @Test("a folded value is replaced whole")
    func replacesFoldedValue() {
        let original = """
            destination_directory: /Users/x/Library/Mobile Documents/60-69
              Work & Career/62 Files/Meetings
            llm_provider: claude
            """
        let updated = Configuration.apply(["destination_directory": "/tmp/new"], to: original)
        #expect(!updated.contains("Work & Career"))
        #expect(updated.contains("llm_provider: claude"))
        #expect(Configuration.scalars(in: updated)["destination_directory"] == "/tmp/new")
    }

    @Test("a key the file lacks is appended")
    func appendsNewKey() {
        let updated = Configuration.apply(["slack_webhook_url": "https://hooks.slack.com/x"],
                                          to: "llm_provider: claude")
        let values = Configuration.scalars(in: updated)
        #expect(values["llm_provider"] == "claude")
        #expect(values["slack_webhook_url"] == "https://hooks.slack.com/x")
    }

    @Test("writing to an empty file works")
    func emptyFile() {
        #expect(Configuration.scalars(in: Configuration.apply(["a": "b"], to: ""))["a"] == "b")
    }

    /// Nested maps and lists are not modelled, so they must pass through
    /// untouched rather than be flattened or dropped.
    @Test("structures this does not model are left alone")
    func leavesStructuresAlone() {
        let original = """
            known_participants:
              - Arno
              - Caleb
            llm_provider: claude
            """
        let updated = Configuration.apply(["llm_provider": "openai"], to: original)
        #expect(updated.contains("  - Arno"))
        #expect(updated.contains("  - Caleb"))
        #expect(updated.contains("llm_provider: openai"))
    }

    @Test(
        "values that would reparse as something else are quoted",
        arguments: [
            ("", "\"\""),
            ("plain value", "plain value"),
            ("/tmp/a b/c", "/tmp/a b/c"),
            ("key: value", "\"key: value\""),
            ("trailing ", "\"trailing \""),
            ("has #hash", "\"has #hash\""),
            ("has # comment", "\"has # comment\""),
        ])
    func quoting(value: String, expected: String) {
        let updated = Configuration.apply(["k": value], to: "k: old")
        #expect(updated.trimmingCharacters(in: .whitespacesAndNewlines) == "k: \(expected)")
    }

    /// Whatever the quoting does, reading it back must give the value handed in.
    @Test(
        "every value round trips",
        arguments: [
            "plain", "/Users/x/Mobile Documents/60-69 Work & Career/Meetings",
            "key: value", "sk-ant-abc123", "https://hooks.slack.com/services/A/B/C",
            "has #hash", "0.8", "true",
        ])
    func roundTrip(value: String) {
        let updated = Configuration.apply(["k": value], to: "k: old\nother: keep")
        #expect(Configuration.scalars(in: updated)["k"] == value)
        #expect(Configuration.scalars(in: updated)["other"] == "keep")
    }

    @Test("several keys in one pass")
    func multipleKeys() {
        let updated = Configuration.apply(
            ["llm_provider": "openai", "whisper_model": "medium", "new_key": "x"],
            to: "llm_provider: claude\nwhisper_model: large-v3-turbo\nkeep: me")
        let values = Configuration.scalars(in: updated)
        #expect(values["llm_provider"] == "openai")
        #expect(values["whisper_model"] == "medium")
        #expect(values["new_key"] == "x")
        #expect(values["keep"] == "me")
    }

    /// The file holds API keys, so its mode matters as much as its contents.
    @Test("the written file is not world readable")
    func fileMode() throws {
        let directory = URL(filePath: NSTemporaryDirectory())
            .appending(path: "transcribe-cfg-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appending(path: "config.yaml")
        try Configuration.write(["anthropic_api_key": "sk-ant-secret"], to: url)

        let mode = try #require(
            FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber)
        #expect(mode.int16Value & 0o077 == 0)
        #expect(Configuration.load(from: url).string("anthropic_api_key") == "sk-ant-secret")
    }

    @Test("typed reads fall back when a key is absent or unparseable")
    func typedReads() {
        let config = Configuration(values: ["n": "notanumber", "b": "yes", "d": "0.75"])
        #expect(config.int("n", default: 7) == 7)
        #expect(config.int("missing", default: 7) == 7)
        #expect(config.bool("b", default: false))
        #expect(config.bool("missing", default: true))
        #expect(config.double("d", default: 0.8) == 0.75)
        #expect(config.url("missing") == nil)
    }
}

@Suite("Config lists")
struct ConfigListTests {
    @Test("a block sequence is read")
    func readsSequence() {
        let yaml = """
            known_participants:
              - Arno Bakker
              - Caleb Sargeant
            llm_provider: claude
            """
        #expect(Configuration.sequences(in: yaml)["known_participants"] == ["Arno Bakker", "Caleb Sargeant"])
        // A sequence is not also a scalar; treating it as one wrote it back flattened.
        #expect(Configuration.scalars(in: yaml)["known_participants"] == nil)
        #expect(Configuration.scalars(in: yaml)["llm_provider"] == "claude")
    }

    @Test("a sequence is replaced whole")
    func replacesSequence() {
        let yaml = """
            known_participants:
              - Old One
              - Old Two
            llm_provider: claude
            """
        let updated = Configuration.applyList("known_participants", ["New"], to: yaml)
        #expect(Configuration.sequences(in: updated)["known_participants"] == ["New"])
        #expect(!updated.contains("Old One"))
        #expect(Configuration.scalars(in: updated)["llm_provider"] == "claude")
    }

    @Test("an empty list is written as an empty sequence, not dropped")
    func emptyList() {
        let updated = Configuration.applyList("known_participants", [], to: "known_participants:\n  - A")
        #expect(updated.contains("known_participants: []"))
        #expect(!updated.contains("- A"))
    }

    @Test("a list is appended when the key is absent")
    func appendsList() {
        let updated = Configuration.applyList("known_participants", ["Arno"], to: "llm_provider: claude")
        #expect(Configuration.sequences(in: updated)["known_participants"] == ["Arno"])
        #expect(Configuration.scalars(in: updated)["llm_provider"] == "claude")
    }

    @Test("list items needing quotes round trip")
    func quotedItems() {
        let items = ["Plain Name", "Name: with colon", "with #hash"]
        let updated = Configuration.applyList("known_participants", items, to: "")
        #expect(Configuration.sequences(in: updated)["known_participants"] == items)
    }

    /// A scalar key replaced by a list must not leave the old value behind.
    @Test("replacing a scalar with a list")
    func scalarToList() {
        let updated = Configuration.applyList("known_participants", ["Arno"], to: "known_participants: ''\nkeep: me")
        #expect(Configuration.sequences(in: updated)["known_participants"] == ["Arno"])
        #expect(Configuration.scalars(in: updated)["keep"] == "me")
    }
}

@Suite("Meeting categories")
struct TagTests {
    private func temporaryFolder() -> URL {
        let url = URL(filePath: NSTemporaryDirectory())
            .appending(path: "transcribe-tags-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    @Test("tags round trip through the folder")
    func roundTrip() throws {
        let folder = temporaryFolder()
        defer { try? FileManager.default.removeItem(at: folder) }
        try Tags(names: ["Client", "1:1"]).save(in: folder)
        #expect(Tags.load(in: folder).names == ["Client", "1:1"])
    }

    /// An empty tag file is clutter in a folder the user browses in Finder.
    @Test("clearing every tag removes the file")
    func removesEmptyFile() throws {
        let folder = temporaryFolder()
        defer { try? FileManager.default.removeItem(at: folder) }
        try Tags(names: ["Client"]).save(in: folder)
        try Tags(names: []).save(in: folder)
        #expect(!FileManager.default.fileExists(atPath: folder.appending(path: Tags.filename).path))
    }

    @Test("a folder with no tag file has no tags")
    func missingFile() {
        #expect(Tags.load(in: URL(filePath: "/nonexistent")).names.isEmpty)
    }

    @Test(
        "duplicates differing only in case are one tag",
        arguments: [
            (["Client", "client"], ["Client"]),
            (["  Spaced  ", "Spaced"], ["Spaced"]),
            (["a", "", "  ", "b"], ["a", "b"]),
        ])
    func normalisation(input: [String], expected: [String]) {
        #expect(TagIndex.normalise(input) == expected)
    }
}
