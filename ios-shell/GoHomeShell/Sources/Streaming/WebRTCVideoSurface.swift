import Foundation
import SwiftUI
import WebRTC

final class WebRTCVideoSurface: @unchecked Sendable, Identifiable {
    let id = UUID()
    let renderedFrames: AsyncThrowingStream<TimeInterval, Error>

    private let track: RTCVideoTrack
    private let renderer: CountingVideoRenderer
    private let continuation: AsyncThrowingStream<TimeInterval, Error>.Continuation
    private let lock = NSLock()
    private var attached = false
    private var finished = false

    init(track: RTCVideoTrack) {
        self.track = track
        var capturedContinuation: AsyncThrowingStream<TimeInterval, Error>.Continuation?
        renderedFrames = AsyncThrowingStream(bufferingPolicy: .bufferingNewest(1)) {
            capturedContinuation = $0
        }
        continuation = capturedContinuation!
        let frameContinuation = continuation
        renderer = CountingVideoRenderer {
            frameContinuation.yield(ProcessInfo.processInfo.systemUptime)
        }
    }

    func attach(to target: RTCVideoRenderer) {
        lock.lock()
        let shouldAttach = !finished && !attached
        if shouldAttach { attached = true }
        lock.unlock()
        renderer.setTarget(target)
        if shouldAttach { track.add(renderer) }
    }

    func detach(from target: RTCVideoRenderer) {
        renderer.clearTarget(target)
    }

    func finish(throwing error: Error? = nil) {
        lock.lock()
        guard !finished else {
            lock.unlock()
            return
        }
        finished = true
        let wasAttached = attached
        attached = false
        lock.unlock()
        if wasAttached { track.remove(renderer) }
        renderer.clearTarget(nil)
        if let error {
            continuation.finish(throwing: error)
        } else {
            continuation.finish()
        }
    }
}

struct WebRTCVideoView: UIViewRepresentable {
    let surface: WebRTCVideoSurface

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let view = RTCMTLVideoView(frame: .zero)
        view.backgroundColor = .black
        view.videoContentMode = .scaleAspectFill
        context.coordinator.install(surface: surface, on: view)
        return view
    }

    func updateUIView(_ view: RTCMTLVideoView, context: Context) {
        context.coordinator.install(surface: surface, on: view)
    }

    static func dismantleUIView(_ view: RTCMTLVideoView, coordinator: Coordinator) {
        coordinator.uninstall(from: view)
    }

    final class Coordinator {
        private var surface: WebRTCVideoSurface?

        func install(surface next: WebRTCVideoSurface, on view: RTCMTLVideoView) {
            guard surface?.id != next.id else { return }
            surface?.detach(from: view)
            surface = next
            next.attach(to: view)
        }

        func uninstall(from view: RTCMTLVideoView) {
            surface?.detach(from: view)
            surface = nil
        }
    }
}

private final class CountingVideoRenderer: NSObject, RTCVideoRenderer, @unchecked Sendable {
    private let lock = NSLock()
    private weak var target: RTCVideoRenderer?
    private let onRenderedFrame: @Sendable () -> Void

    init(onRenderedFrame: @escaping @Sendable () -> Void) {
        self.onRenderedFrame = onRenderedFrame
    }

    func setTarget(_ target: RTCVideoRenderer) {
        lock.lock()
        self.target = target
        lock.unlock()
    }

    func clearTarget(_ expectedTarget: RTCVideoRenderer?) {
        lock.lock()
        if expectedTarget == nil || (target as AnyObject?) === (expectedTarget as AnyObject?) {
            target = nil
        }
        lock.unlock()
    }

    func setSize(_ size: CGSize) {
        lock.lock()
        target?.setSize(size)
        lock.unlock()
    }

    func renderFrame(_ frame: RTCVideoFrame?) {
        guard let frame else { return }
        lock.lock()
        guard let target else {
            lock.unlock()
            return
        }
        target.renderFrame(frame)
        onRenderedFrame()
        lock.unlock()
    }
}
