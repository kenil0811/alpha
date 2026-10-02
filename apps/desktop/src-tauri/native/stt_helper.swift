// Tiny native speech-to-text helper, run as a subprocess of the Rust host.
//
// Why a Swift helper instead of Rust `objc2` bindings: SFSpeechRecognizer + AVAudioEngine need
// delegate-style callback plumbing (recognition task results, async authorization) that the
// `objc2-*` crates already in Cargo.lock (app-kit, foundation, ...) do not cover — `objc2-speech`
// and `objc2-av-foundation` are not locked. Pulling them in adds a new dependency subtree (and
// disk for their build artifacts) on a machine that is already low on space. Swift already speaks
// these frameworks directly and ships with Xcode's command-line tools (`swiftc` on PATH), so
// `build.rs` compiles this one file into a small standalone binary; Rust just spawns it and reads
// newline-delimited JSON off its stdout. One process, no new Rust dependency tree.
//
// Protocol (stdout, one JSON object per line, flushed immediately):
//   {"type":"partial","text":"..."}   -- still listening
//   {"type":"final","text":"..."}     -- utterance settled; the helper then exits 0
//   {"type":"error","text":"..."}     -- permission denied, no mic, recognizer unavailable, etc.
// SIGTERM/SIGINT (sent by the host's stt_stop) ends the audio cleanly so a trailing "final" (or
// "error") is still emitted before the process exits.

import Foundation
import AVFoundation
import Speech

setbuf(stdout, nil)

func emit(_ kind: String, _ text: String) {
    let escaped = text
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
        .replacingOccurrences(of: "\n", with: "\\n")
    print("{\"type\":\"\(kind)\",\"text\":\"\(escaped)\"}")
}

func fail(_ message: String) -> Never {
    emit("error", message)
    exit(1)
}

let localeId = ProcessInfo.processInfo.environment["ALPHA_STT_LOCALE"] ?? "en-US"
guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: localeId)), recognizer.isAvailable else {
    fail("Speech recognition isn't available for this language on this Mac.")
}

let sem = DispatchSemaphore(value: 0)
var speechDenied = false
SFSpeechRecognizer.requestAuthorization { status in
    speechDenied = status != .authorized
    sem.signal()
}
sem.wait()
if speechDenied {
    fail("permission_denied: speech recognition")
}

let micSem = DispatchSemaphore(value: 0)
var micDenied = false
switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .authorized:
    micSem.signal()
case .notDetermined:
    AVCaptureDevice.requestAccess(for: .audio) { granted in
        micDenied = !granted
        micSem.signal()
    }
default:
    micDenied = true
    micSem.signal()
}
micSem.wait()
if micDenied {
    fail("permission_denied: microphone")
}

let audioEngine = AVAudioEngine()
let request = SFSpeechAudioBufferRecognitionRequest()
request.shouldReportPartialResults = true

let inputNode = audioEngine.inputNode
let format = inputNode.outputFormat(forBus: 0)
inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
    request.append(buffer)
}
audioEngine.prepare()
do {
    try audioEngine.start()
} catch {
    fail("Could not start the microphone: \(error.localizedDescription)")
}

func stopEngine() {
    if audioEngine.isRunning {
        audioEngine.stop()
        inputNode.removeTap(onBus: 0)
    }
}

let sigSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
sigSource.setEventHandler {
    stopEngine()
    request.endAudio()
}
sigSource.resume()
signal(SIGTERM, SIG_IGN)
let sigSourceInt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sigSourceInt.setEventHandler {
    stopEngine()
    request.endAudio()
}
sigSourceInt.resume()
signal(SIGINT, SIG_IGN)

recognizer.recognitionTask(with: request) { result, error in
    if let result = result {
        let text = result.bestTranscription.formattedString
        emit(result.isFinal ? "final" : "partial", text)
        if result.isFinal {
            stopEngine()
            exit(0)
        }
    }
    if let error = error {
        // `endAudio()` on a deliberate stop also surfaces as an error here once no speech was
        // captured yet; that is a normal "stopped before anything was said", not a failure.
        let message = error.localizedDescription
        stopEngine()
        if message.localizedCaseInsensitiveContains("no speech") {
            emit("final", "")
            exit(0)
        }
        fail(message)
    }
}

RunLoop.main.run()
