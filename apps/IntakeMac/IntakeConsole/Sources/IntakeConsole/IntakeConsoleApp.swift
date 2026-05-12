import SwiftUI

@main
struct IntakeConsoleApp: App {
    let backendURL = URL(string: "http://127.0.0.1:8000")!
    
    @StateObject private var healthClient: BackendHealthClient
    @StateObject private var launcher: BackendLauncher
    
    init() {
        let url = URL(string: "http://127.0.0.1:8000")!
        _healthClient = StateObject(wrappedValue: BackendHealthClient(url: url))
        _launcher = StateObject(wrappedValue: BackendLauncher(mode: .development))
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView(healthClient: healthClient, launcher: launcher, backendURL: backendURL)
                .frame(minWidth: 800, minHeight: 600)
        }
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unified)
    }
}
