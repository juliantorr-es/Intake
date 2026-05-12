import Foundation

enum BackendStatus: String {
    case starting
    case online
    case offline
    case failed
    
    var displayName: String {
        self.rawValue.capitalized
    }
    
    var colorName: String {
        switch self {
        case .starting: return "amber"
        case .online: return "green"
        case .offline: return "gray"
        case .failed: return "red"
        }
    }
}
