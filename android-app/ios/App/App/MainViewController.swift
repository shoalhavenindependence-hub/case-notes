import Capacitor

/// Registers the app's own plugins (those not installed from npm).
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(AppLockPlugin())
    }
}
