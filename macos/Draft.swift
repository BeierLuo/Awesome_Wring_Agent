import Cocoa
import WebKit

final class DraftApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var process: Process?
    var timer: Timer?
    var temporary: URL?
    var baseURL: URL?
    var project: URL!
    var support: URL!
    var dataRoot: URL!
    var downloads: [ObjectIdentifier: (URL, URL)] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于 Caret", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(withTitle: "在 Finder 中显示应用数据", action: #selector(showProject), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 Caret", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出 Caret", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let appItem = NSMenuItem(); appItem.submenu = appMenu; menu.addItem(appItem)
        let edit = NSMenu(title: "编辑")
        for (title, selector, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        let editItem = NSMenuItem(); editItem.submenu = edit; menu.addItem(editItem)
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 940), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Caret"
        window.minSize = NSSize(width: 900, height: 600)
        window.setFrameAutosaveName("DraftMainWindow")
        window.center()
        web = WKWebView(frame: .zero)
        web.navigationDelegate = self; web.uiDelegate = self
        window.contentView = web
        web.loadHTMLString("<body style='background:#ffffff;font:20px system-ui;padding:60px;color:#444'>正在启动 Caret…</body>", baseURL: nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        project = Bundle.main.resourceURL!.appendingPathComponent("app")
        support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Draft")
        dataRoot = support.appendingPathComponent("data")
        guard FileManager.default.isExecutableFile(atPath: support.appendingPathComponent("runtime/bin/python3.12").path) else {
            fail("本机运行环境尚未准备好。请先完成 Caret 的首次环境安装，再打开应用。运行环境位置：" + support.path); return
        }
        // Reuse an already-running browser server only when it serves this workspace.
        var request = URLRequest(url: URL(string: "http://127.0.0.1:18768/api/health")!)
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let health = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async {
                if health?["app"] as? String == "paper-local", health?["root"] as? String == self.dataRoot.appendingPathComponent("workspaces").resolvingSymlinksInPath().path {
                    self.load(URL(string: "http://127.0.0.1:18768/")!)
                } else { self.startServer() }
            }
        }.resume()
    }

    func startServer() {
        do {
            let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("draft-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            temporary = tmp
            let ready = tmp.appendingPathComponent("ready.json")
            let log = dataRoot.appendingPathComponent(".local/mac-app.log")
            try FileManager.default.createDirectory(at: log.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600]) }
            let output = try FileHandle(forWritingTo: log); output.seekToEndOfFile()
            let child = Process()
            child.executableURL = support.appendingPathComponent("runtime/bin/python3.12")
            child.arguments = ["-I", "-B", Bundle.main.resourceURL!.appendingPathComponent("serve.py").path, project.path, ready.path, dataRoot.path, "18768"]
            child.currentDirectoryURL = dataRoot
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (env["PATH"] ?? "")
            env["PYTHONUNBUFFERED"] = "1"
            env["DRAFT_TOOLS_DIR"] = support.appendingPathComponent("tools").path
            child.environment = env; child.standardOutput = output; child.standardError = output
            process = child
            try child.run()
            try? output.close()
            let deadline = Date().addingTimeInterval(30)
            timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { timer in
                if let data = try? Data(contentsOf: ready), let json = try? JSONSerialization.jsonObject(with: data) as? [String: String], let raw = json["url"], let url = URL(string: raw) {
                    timer.invalidate(); self.load(url)
                } else if !child.isRunning || Date() > deadline {
                    timer.invalidate(); self.fail("本地服务启动失败，请查看应用数据目录中的 .local/mac-app.log。"); if child.isRunning { child.terminate() }
                }
            }
        } catch { fail("无法启动本地服务：\(error.localizedDescription)") }
    }
    func load(_ url: URL) { baseURL = url; web.load(URLRequest(url: url)) }
    func fail(_ message: String) { let alert = NSAlert(); alert.messageText = "Caret"; alert.informativeText = message; alert.runModal() }
    @objc func about() { let alert = NSAlert(); alert.messageText = "Caret · 本地论文写作工作区"; alert.informativeText = "本机 macOS 应用。论文、规则与 API 设置保存在 Application Support/Draft/data；运行环境独立保存在本机。"; alert.runModal() }
    @objc func showProject() { if let dataRoot = dataRoot { NSWorkspace.shared.open(dataRoot) } }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { window.makeKeyAndOrderFront(nil); return true }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        if let child = process, child.isRunning { child.terminate() }
        if let tmp = temporary { try? FileManager.default.removeItem(at: tmp) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        let local = url.scheme == "http" && url.host == baseURL?.host && url.port == baseURL?.port
        if local || url.scheme == "blob" || url.absoluteString == "about:blank" {
            decisionHandler(action.shouldPerformDownload ? .download : .allow)
        } else {
            if ["https", "http", "mailto"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, ["http", "https"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let attachment = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().hasPrefix("attachment") ?? false
        decisionHandler(attachment || !response.canShowMIMEType ? .download : .allow)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel(); panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { result in
            guard result == .OK, let destination = panel.url else { completionHandler(nil); return }
            // WebKit requires a nonexistent destination; replace only after a complete download.
            let staging = destination.deletingLastPathComponent().appendingPathComponent(".draft-download-" + UUID().uuidString)
            self.downloads[ObjectIdentifier(download)] = (staging, destination)
            completionHandler(staging)
        }
    }
    func downloadDidFinish(_ download: WKDownload) {
        guard let (staging, destination) = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        do {
            if FileManager.default.fileExists(atPath: destination.path) { _ = try FileManager.default.replaceItemAt(destination, withItemAt: staging) }
            else { try FileManager.default.moveItem(at: staging, to: destination) }
        } catch { fail("导出保存失败：\(error.localizedDescription)") }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let (staging, _) = downloads.removeValue(forKey: ObjectIdentifier(download)) { try? FileManager.default.removeItem(at: staging) }
        if (error as NSError).code != NSURLErrorCancelled { fail("导出失败：\(error.localizedDescription)") }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = parameters.allowsMultipleSelection; panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.beginSheetModal(for: window) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消"); alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = NSAlert(); alert.messageText = prompt; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消")
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24)); input.stringValue = defaultText ?? ""; alert.accessoryView = input
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? input.stringValue : nil) }
    }
}
let application = NSApplication.shared
let delegate = DraftApp()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
