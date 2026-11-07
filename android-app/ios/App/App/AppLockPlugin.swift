import Capacitor
import LocalAuthentication

/// Shows the iPhone's own unlock prompt (Face ID, Touch ID, or the passcode)
/// for the app's optional lock screen. Same calls as the Android AppLock plugin.
@objc(AppLockPlugin)
public class AppLockPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AppLockPlugin"
    public let jsName = "AppLock"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "available", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "verify", returnType: CAPPluginReturnPromise)
    ]

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
