import AVKit
import SwiftUI

/// `AVPlayerView` rather than SwiftUI's `VideoPlayer`.
///
/// `VideoPlayer` gives no way to keep a player across view updates, and this
/// screen needs the transcript to seek the same player the user is watching.
/// `AVPlayerView` also brings the macOS transport controls, including the
/// scrubber and the audio track picker, which matters for OBS recordings that
/// carry more than one audio track.
struct VideoPlayerView: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .inline
        view.videoGravity = .resizeAspect
        view.showsFullScreenToggleButton = true
        view.player = player
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }

    static func dismantleNSView(_ view: AVPlayerView, coordinator: ()) {
        view.player?.pause()
        view.player = nil
    }
}
