import XCTest
@testable import IntakeConsole

final class IntakeConsoleTests: XCTestCase {
    func testAllowedHosts() throws {
        let allowedHosts = ["127.0.0.1", "localhost"]
        
        for host in allowedHosts {
            let url = URL(string: "http://\(host):8000/")!
            XCTAssertTrue(isAllowed(url: url), "Host \(host) should be allowed")
        }
    }
    
    func testRejectedHosts() throws {
        let rejectedHosts = ["google.com", "intake.app", "192.168.1.1"]
        
        for host in rejectedHosts {
            let url = URL(string: "http://\(host)/")!
            XCTAssertFalse(isAllowed(url: url), "Host \(host) should be rejected")
        }
    }
    
    private func isAllowed(url: URL) -> Bool {
        guard let host = url.host else { return false }
        return host == "127.0.0.1" || host == "localhost"
    }
}
