import Foundation
import Combine

enum AuthState: Equatable {
    case locked
    case unlocking
    case unlocked(expiresAt: Date)
    case failed(reason: String)
    
    var isUnlocked: Bool {
        if case .unlocked(let expiresAt) = self {
            return expiresAt > Date()
        }
        return false
    }
}

class LocalAuthorizationState: ObservableObject {
    @Published var state: AuthState = .locked
    
    private var timer: AnyCancellable?
    private let defaultTTL: TimeInterval = 120 // 2 minutes
    
    func unlock(expiresIn: TimeInterval? = nil) {
        let ttl = expiresIn ?? defaultTTL
        let expiry = Date().addingTimeInterval(ttl)
        self.state = .unlocked(expiresAt: expiry)
        
        // Schedule auto-lock
        timer?.cancel()
        timer = Just(())
            .delay(for: .seconds(ttl), scheduler: RunLoop.main)
            .sink { [weak self] _ in
                self?.lock()
            }
        
        print("LocalAuthorizationState: Unlocked. Expiry: \(expiry)")
    }
    
    func lock() {
        timer?.cancel()
        self.state = .locked
        print("LocalAuthorizationState: Locked.")
    }
    
    func setUnlocking() {
        self.state = .unlocking
    }
    
    func setFailed(reason: String) {
        self.state = .failed(reason: reason)
    }
    
    var timeRemaining: TimeInterval {
        if case .unlocked(let expiresAt) = state {
            return max(0, expiresAt.timeIntervalSince(Date()))
        }
        return 0
    }
}
