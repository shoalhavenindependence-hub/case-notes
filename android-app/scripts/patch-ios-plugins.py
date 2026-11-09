#!/usr/bin/env python3
"""Make the iPhone speech plugins safe to use one after the other (Carla talks, then listens).

Run after `npm ci`, before building the iPhone app. Edits files in node_modules in place,
and is safe to run more than once.

1. @capacitor-community/speech-recognition: remove any old microphone tap before adding a new
   one, refuse to start (instead of crashing) when the microphone has no usable audio format,
   and fully release the microphone and audio session on stop, so the phone's voice can play.
2. @capacitor-community/text-to-speech: the list of waiting speak() calls was changed from two
   threads at once; keep every change to it on the main thread.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'node_modules' / '@capacitor-community'


def patch(path, pairs):
    p = ROOT / path
    s = p.read_text()
    if 'CNK-PATCHED' in s:
        print('already patched:', path)
        return
    for old, new in pairs:
        if old not in s:
            sys.exit('patch-ios-plugins: expected text not found in %s: %s' % (path, old[:80]))
        s = s.replace(old, new, 1)
    p.write_text('// CNK-PATCHED\n' + s)
    print('patched:', path)


patch('speech-recognition/ios/Plugin/Plugin.swift', [
    # The crash (TestFlight report, build 15): a result from the previous listen set
    # recognitionRequest to nil just before it was force-unwrapped. Use a local copy.
    ("""            self.recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
            self.recognitionRequest?.shouldReportPartialResults = partialResults
""", """            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = partialResults
            self.recognitionRequest = request
"""),
    ("""recognitionTask(with: self.recognitionRequest!, resultHandler:""", """recognitionTask(with: request, resultHandler:"""),
    ("""                self.recognitionRequest?.append(buffer)""", """                request.append(buffer)"""),
    # Guard the microphone tap.
    ("""            let inputNode: AVAudioInputNode = self.audioEngine!.inputNode
            let format: AVAudioFormat = inputNode.outputFormat(forBus: 0)
""", """            let inputNode: AVAudioInputNode = self.audioEngine!.inputNode
            let format: AVAudioFormat = inputNode.outputFormat(forBus: 0)
            if format.sampleRate <= 0 || format.channelCount == 0 {
                call.reject("Microphone is not ready. Please try again.")
                return
            }
"""),
    ("""            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) {""",
     """            inputNode.removeTap(onBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) {"""),
    # Results from an old, cancelled listen must not touch the new one.
    ("""            self.recognitionTask = self.speechRecognizer?.recognitionTask(with: request, resultHandler: { (result, error) in
""", """            let myEngine = self.audioEngine
            self.recognitionTask = self.speechRecognizer?.recognitionTask(with: request, resultHandler: { (result, error) in
                if myEngine !== self.audioEngine { return }
"""),
    ("""                    if result!.isFinal {
                        self.audioEngine!.stop()""", """                    if result!.isFinal {
                        self.audioEngine?.stop()"""),
    ("""                if error != nil {
                    self.audioEngine!.stop()""", """                if error != nil {
                    self.audioEngine?.stop()"""),
    # Stop: release the microphone and hand the audio back for the phone's voice.
    ("""            if let engine = self.audioEngine, engine.isRunning {
                engine.stop()
                self.recognitionRequest?.endAudio()
                self.notifyListeners("listeningState", data: ["status": "stopped"])
            }
            call.resolve()""", """            if let engine = self.audioEngine, engine.isRunning {
                engine.stop()
                engine.inputNode.removeTap(onBus: 0)
                self.recognitionRequest?.endAudio()
                self.notifyListeners("listeningState", data: ["status": "stopped"])
            }
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            call.resolve()"""),
])

patch('text-to-speech/ios/Sources/TextToSpeechPlugin/TextToSpeech.swift', [
    ("""        if queueStrategy == QUEUE_STRATEGY.QUEUE_FLUSH.rawValue {
            self.synthesizer.stopSpeaking(at: .immediate)
        }""", """        if queueStrategy == QUEUE_STRATEGY.QUEUE_FLUSH.rawValue {
            DispatchQueue.main.async { self.synthesizer.stopSpeaking(at: .immediate) }
        }"""),
    ("""    @objc public func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }""", """    @objc public func stop() {
        DispatchQueue.main.async { self.synthesizer.stopSpeaking(at: .immediate) }
    }"""),
    ("""        self.calls.append(call)
""", """        DispatchQueue.main.async { self.calls.append(call) }
"""),
    ("""        synthesizer.speak(utterance)
    }""", """        DispatchQueue.main.async { self.synthesizer.speak(utterance) }
    }"""),
    ("""    @objc private func resolveCurrentCall() {
        guard let call = calls.first else {
            return
        }
        call.resolve()
        calls.removeFirst()
    }""", """    @objc private func resolveCurrentCall() {
        DispatchQueue.main.async {
            guard !self.calls.isEmpty else { return }
            let call = self.calls.removeFirst()
            call.resolve()
        }
    }"""),
])
