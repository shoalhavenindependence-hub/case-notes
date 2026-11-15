import Capacitor
import LocalAuthentication
import AVFoundation

/// Shows the iPhone's own unlock prompt (Face ID, Touch ID, or the passcode)
/// for the app's optional lock screen. Same calls as the Android AppLock plugin.
@objc(AppLockPlugin)
public class AppLockPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AppLockPlugin"
    public let jsName = "AppLock"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "available", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "verify", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "keepAwake", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "beep", returnType: CAPPluginReturnPromise)
    ]
    private var beepPlayer: AVAudioPlayer?

    /// The Dictate start/stop beep. Played natively so it sounds even with the silent switch on
    /// and isn't cut off when the microphone takes over the audio.
    @objc func beep(_ call: CAPPluginCall) {
        let up = call.getBool("up") ?? true
        DispatchQueue.main.async {
            let session = AVAudioSession.sharedInstance()
            try? session.setCategory(.playAndRecord, options: [.defaultToSpeaker, .mixWithOthers])
            try? session.setActive(true)
            let rate = 44100.0, dur = 0.2
            let n = Int(rate * dur)
            var pcm = Data(capacity: n * 2)
            var phase = 0.0
            for i in 0..<n {
                let t = Double(i) / rate
                let k = min(t / 0.15, 1.0)
                let f = up ? 660 + 220 * k : 880 - 220 * k
                phase += 2 * Double.pi * f / rate
                let env = t < 0.02 ? t / 0.02 : max(0, 1 - (t - 0.02) / 0.16)
                var v = Int16(sin(phase) * env * 0.5 * 32767).littleEndian
                withUnsafeBytes(of: &v) { pcm.append(contentsOf: $0) }
            }
            var wav = Data()
            func u32(_ x: UInt32) { var y = x.littleEndian; withUnsafeBytes(of: &y) { wav.append(contentsOf: $0) } }
            func u16(_ x: UInt16) { var y = x.littleEndian; withUnsafeBytes(of: &y) { wav.append(contentsOf: $0) } }
            wav.append("RIFF".data(using: .ascii)!); u32(UInt32(36 + pcm.count))
            wav.append("WAVEfmt ".data(using: .ascii)!); u32(16); u16(1); u16(1)
            u32(UInt32(rate)); u32(UInt32(rate) * 2); u16(2); u16(16)
            wav.append("data".data(using: .ascii)!); u32(UInt32(pcm.count)); wav.append(pcm)
            self.beepPlayer = try? AVAudioPlayer(data: wav)
            self.beepPlayer?.volume = 1.0
            self.beepPlayer?.play()
            call.resolve()
        }
    }

    /// Stops the screen going to sleep while Carla is open ({on: true}), and lets it sleep again ({on: false}).
    @objc func keepAwake(_ call: CAPPluginCall) {
        let on = call.getBool("on") ?? false
        DispatchQueue.main.async {
            UIApplication.shared.isIdleTimerDisabled = on
            call.resolve()
        }
    }

    @objc func available(_ call: CAPPluginCall) {
        var error: NSError?
        let ok = LAContext().canEvaluatePolicy(.deviceOwnerAuthentication, error: &error)
        call.resolve(["available": ok])
    }

    @objc func verify(_ call: CAPPluginCall) {
        let reason = call.getString("reason") ?? "Unlock your case notes"
        LAContext().evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, error in
            if success {
                call.resolve()
            } else {
                let code = (error as? LAError)?.code.rawValue ?? -1
                call.reject(error?.localizedDescription ?? "Not unlocked", String(code))
            }
        }
    }
}
