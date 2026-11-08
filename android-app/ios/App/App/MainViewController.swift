import Capacitor

/// Registers the app's own plugins (those not installed from npm).
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(AppLockPlugin())
        // Google Drive backup appears only once the Google iOS client ID is set in Info.plist.
        if GoogleDrivePlugin.isConfigured {
            bridge?.registerPluginInstance(GoogleDrivePlugin())
        }
    }
}
