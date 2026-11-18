import Foundation
import AVFoundation
import Speech

guard CommandLine.arguments.count > 1 else {
    print("Usage: mac_voice_helper <record_seconds>")
    exit(1)
}

let seconds = Double(CommandLine.arguments[1]) ?? 5.0
let tempWav = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("macassistant_ptt.wav")

let settings: [String: Any] = [
    AVFormatIDKey: Int(kAudioFormatLinearPCM),
    AVSampleRateKey: 16000.0,
    AVNumberOfChannelsKey: 1,
    AVLinearPCMBitDepthKey: 16,
    AVLinearPCMIsBigEndianKey: false,
    AVLinearPCMIsFloatKey: false
]

do {
    let recorder = try AVAudioRecorder(url: tempWav, settings: settings)
    recorder.record()
    Thread.sleep(forTimeInterval: seconds)
    recorder.stop()
} catch {
    fputs("Recording error: \(error)\n", stderr)
    exit(1)
}

// Perform on-device speech recognition via SFSpeechRecognizer
guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    exit(0)
}

recognizer.supportsOnDeviceRecognition = true
let request = SFSpeechURLRecognitionRequest(url: tempWav)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = false

let semaphore = DispatchSemaphore(value: 0)
var resultText = ""

recognizer.recognitionTask(with: request) { result, error in
    if let result = result, result.isFinal {
        resultText = result.bestTranscription.formattedString
        semaphore.signal()
    } else if error != nil {
        semaphore.signal()
    }
}

_ = semaphore.wait(timeout: .now() + 4.0)
print(resultText)

// Cleanup temp recording
try? FileManager.default.removeItem(at: tempWav)
