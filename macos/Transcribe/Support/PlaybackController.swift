import AVFoundation
import Foundation

/// Owns the `AVPlayer` for one meeting so the transcript can drive it.
///
/// Clicking a transcript line seeks the recording, which is the one interaction
/// that makes a transcript worth reading next to the video rather than instead
/// of it. That needs a single player both views hold, not a `VideoPlayer` that
/// makes its own.
@MainActor
@Observable
final class PlaybackController {
    enum Phase: Equatable {
        case none
        case checking
        case ready
        case unplayable(String)
    }

    private(set) var phase: Phase = .none
    private(set) var player: AVPlayer?
    private(set) var url: URL?

    /// Discards the result of a check that a newer one has superseded.
    private var loadID = 0

    func open(_ url: URL?) async {
        loadID += 1
        let id = loadID
        teardown()

        guard let url else {
            phase = .none
            return
        }

        self.url = url
        phase = .checking

        let asset = AVURLAsset(url: url)
        do {
            let playable = try await asset.load(.isPlayable)
            guard id == loadID else { return }
            guard playable else {
                // OBS writes .qta containers carrying Apple Positional Audio
                // and timed-metadata tracks. Whether AVFoundation opens one is
                // not something this can assume, so it reports rather than
                // silently showing an empty frame.
                phase = .unplayable("\(url.pathExtension.uppercased()) is not playable here.")
                return
            }
            let item = AVPlayerItem(asset: asset)
            player = AVPlayer(playerItem: item)
            phase = .ready
        } catch is CancellationError {
            return
        } catch {
            guard id == loadID else { return }
            phase = .unplayable(error.localizedDescription)
        }
    }

    /// Seek to a point measured from the start of the *recording*.
    ///
    /// Segment times are relative to the recording, and a split meeting's clip
    /// starts partway through it, so the clip's own offset is subtracted.
    func seek(toRecordingSecond second: Double, meetingStart: Double) {
        guard let player else { return }
        let target = max(second - meetingStart, 0)
        player.seek(
            to: CMTime(seconds: target, preferredTimescale: 600),
            toleranceBefore: .zero,
            toleranceAfter: .zero
        )
        player.play()
    }

    func teardown() {
        player?.pause()
        player = nil
        url = nil
    }
}
