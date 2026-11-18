import Foundation
import Speech

guard CommandLine.arguments.count > 1 else {
    fputs("Usage: apple_stt <audio_file_path>\n", stderr)
    exit(1)
}

let audioPath = CommandLine.arguments[1]
let fileURL = URL(fileURLWithPath: audioPath)

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    fputs("Speech recognizer unavailable\n", stderr)
    exit(1)
}

// Request strictly on-device speech recognition without cloud transmission
recognizer.supportsOnDeviceRecognition = true

let request = SFSpeechURLRecognitionRequest(url: fileURL)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = false

let semaphore = DispatchSemaphore(value: 0)
var transcribedText = ""

recognizer.recognitionTask(with: request) { result, error in
    if let result = result, result.isFinal {
        transcribedText = result.bestTranscription.formattedString
        semaphore.signal()
    } else if error != nil {
        semaphore.signal()
    }
}

// Wait up to 5 seconds
_ = semaphore.wait(timeout: .now() + 5.0)
print(transcribedText)
