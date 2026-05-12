import Foundation

@MainActor
class BackendHealthClient: ObservableObject {
    @Published var status: BackendStatus = .offline
    private let url: URL
    private var timer: Timer?
    
    init(url: URL) {
        self.url = url
    }
    
    func startMonitoring() {
        checkHealth()
        timer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.checkHealth()
            }
        }
    }
    
    func stopMonitoring() {
        timer?.invalidate()
        timer = nil
    }
    
    func checkHealth() {
        var request = URLRequest(url: url.appendingPathComponent("api/local/health"))
        request.timeoutInterval = 2.0
        
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            Task { @MainActor in
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                    self?.status = .online
                } else {
                    self?.status = .offline
                }
            }
        }.resume()
    }
}
