import Capacitor
import GoogleSignIn

/// Signs in with Google and hands the app a Drive access token (drive.file scope only:
/// the app can see just the files it made). Same calls as the Android GoogleDrive plugin.
@objc(GoogleDrivePlugin)
public class GoogleDrivePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "GoogleDrivePlugin"
    public let jsName = "GoogleDrive"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "authorize", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearToken", returnType: CAPPluginReturnPromise)
    ]

    static let driveFile = "https://www.googleapis.com/auth/drive.file"

    /// The iOS OAuth client ID from Google Cloud, set in Info.plist as GIDClientID.
    static var isConfigured: Bool {
        let id = Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String ?? ""
        return id.hasSuffix(".apps.googleusercontent.com")
    }

    @objc func authorize(_ call: CAPPluginCall) {
        let interactive = call.getBool("interactive") ?? false
        DispatchQueue.main.async {
            let gid = GIDSignIn.sharedInstance
            if let user = gid.currentUser {
                self.withScope(user, call, interactive)
                return
            }
            gid.restorePreviousSignIn { user, _ in
                if let user = user {
                    self.withScope(user, call, interactive)
                } else if !interactive {
                    call.reject("Google needs the person to sign in again", "consent_required")
                } else {
                    guard let vc = self.bridge?.viewController else { call.reject("No screen to show sign-in", "failed"); return }
                    gid.signIn(withPresenting: vc, hint: nil, additionalScopes: [GoogleDrivePlugin.driveFile]) { result, error in
                        if let user = result?.user { self.withScope(user, call, interactive) }
                        else { self.fail(call, error) }
                    }
                }
            }
        }
    }

    /// Google's iOS library refreshes tokens itself; nothing to clear beyond forcing a refresh next time.
    @objc func clearToken(_ call: CAPPluginCall) {
        call.resolve()
    }

    private func withScope(_ user: GIDGoogleUser, _ call: CAPPluginCall, _ interactive: Bool) {
        if user.grantedScopes?.contains(GoogleDrivePlugin.driveFile) == true {
            user.refreshTokensIfNeeded { user, error in
                if let token = user?.accessToken.tokenString, !token.isEmpty { call.resolve(["accessToken": token]) }
                else { self.fail(call, error) }
            }
            return
        }
        guard interactive, let vc = bridge?.viewController else {
            call.reject("Google needs the person to sign in again", "consent_required")
            return
        }
        user.addScopes([GoogleDrivePlugin.driveFile], presenting: vc) { result, error in
            if let token = result?.user.accessToken.tokenString { call.resolve(["accessToken": token]) }
            else { self.fail(call, error) }
        }
    }

    private func fail(_ call: CAPPluginCall, _ error: Error?) {
        if let e = error as NSError?, e.domain == kGIDSignInErrorDomain, e.code == GIDSignInError.canceled.rawValue {
            call.reject("Sign-in was cancelled", "cancelled")
        } else {
            call.reject("Google sign-in failed: " + (error?.localizedDescription ?? "unknown"), "failed")
        }
    }
}
