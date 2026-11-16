import Capacitor
import Foundation

/// Automatic iCloud backup for the iPhone app. No sign-in: it uses the iCloud account already on the phone.
/// Writes two files to iCloud Drive › Case Note Keeper (visible in the Files app):
///   "Case Note Keeper backup.json"  everything the app needs to restore notes on a new iPhone
///   "All case notes.csv"            a spreadsheet of every note, to open in Numbers or Excel
@objc(ICloudBackupPlugin)
public class ICloudBackupPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ICloudBackupPlugin"
    public let jsName = "ICloudBackup"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "save", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "load", returnType: CAPPluginReturnPromise)
    ]

    static let containerID = "iCloud.com.shoalhavenindependence.casenotes"
    static let backupName = "Case Note Keeper backup.json"
    static let sheetName = "All case notes.csv"
    static let offMessage = "Not backing up to iCloud. To turn it on, open the Settings app, tap your name, then iCloud, and turn on iCloud Drive."

    private let queue = DispatchQueue(label: "casenotes.icloud-backup")

    /// The app's Documents folder in iCloud Drive, or nil when iCloud Drive is off.
    private func folder() -> URL? {
        let fm = FileManager.default
        guard fm.ubiquityIdentityToken != nil,
              let root = fm.url(forUbiquityContainerIdentifier: Self.containerID) else { return nil }
        let docs = root.appendingPathComponent("Documents", isDirectory: true)
        try? fm.createDirectory(at: docs, withIntermediateDirectories: true)
        return docs
    }

    private func write(_ text: String, to url: URL) throws {
        var coordError: NSError?
        var writeError: Error?
        NSFileCoordinator(filePresenter: nil).coordinate(writingItemAt: url, options: .forReplacing, error: &coordError) { u in
            do { try Data(text.utf8).write(to: u, options: .atomic) } catch { writeError = error }
        }
        if let e = coordError { throw e }
        if let e = writeError { throw e }
    }

    @objc func save(_ call: CAPPluginCall) {
        let json = call.getString("json") ?? ""
        let csv = call.getString("csv") ?? ""
        queue.async {
            guard let dir = self.folder() else { call.reject(Self.offMessage); return }
            do {
                if !json.isEmpty { try self.write(json, to: dir.appendingPathComponent(Self.backupName)) }
                if !csv.isEmpty { try self.write(csv, to: dir.appendingPathComponent(Self.sheetName)) }
                call.resolve()
            } catch {
                call.reject("The iCloud backup didn't save: \(error.localizedDescription)")
            }
        }
    }

    /// Returns {json} from the iCloud backup, downloading it first if this is a new iPhone. {} if there is none.
    @objc func load(_ call: CAPPluginCall) {
        queue.async {
            guard let dir = self.folder() else { call.resolve([:]); return }
            let fm = FileManager.default
            let url = dir.appendingPathComponent(Self.backupName)
            // On a new iPhone the file may still be only in iCloud: ask for it and wait up to 30 seconds.
            let deadline = Date().addingTimeInterval(30)
            while Date() < deadline {
                try? fm.startDownloadingUbiquitousItem(at: url)
                if fm.fileExists(atPath: url.path) {
                    let status = (try? url.resourceValues(forKeys: [.ubiquitousItemDownloadingStatusKey]))?.ubiquitousItemDownloadingStatus
                    if status == nil || status == .current || status == .downloaded { break }
                }
                Thread.sleep(forTimeInterval: 0.5)
            }
            guard fm.fileExists(atPath: url.path) else { call.resolve([:]); return }
            var text: String?
            var coordError: NSError?
            NSFileCoordinator(filePresenter: nil).coordinate(readingItemAt: url, options: [], error: &coordError) { u in
                text = try? String(contentsOf: u, encoding: .utf8)
            }
            if let t = text { call.resolve(["json": t]) } else { call.resolve([:]) }
        }
    }
}
