import SwiftUI
import Combine

enum UnlockResult {
    case success
    case failed(reason: String)
    case cancelled
    case unavailable
}

class LocalAuthorizationState: ObservableObject {
    @Published var isUnlocked: Bool = false
    @Published var lastError: String?
    @Published var lastUnlockTime: Date?
    
    func unlock() {
        isUnlocked = true
        lastError = nil
        lastUnlockTime = Date()
    }
    
    func lock() {
        isUnlocked = false
        lastUnlockTime = nil
    }
    
    func setFailed(reason: String) {
        isUnlocked = false
        lastError = reason
        lastUnlockTime = nil
    }
}
