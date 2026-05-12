import SwiftUI

enum IntakeTheme {
    static let radiusWindow: CGFloat = 18
    static let radiusPanel: CGFloat = 14
    static let radiusCard: CGFloat = 12
    static let radiusChip: CGFloat = 999
    
    enum Colors {
        static let bg = Color(hex: "101010")
        static let panel = Color.white.opacity(0.075)
        static let paper = Color(hex: "f4efe7")
        static let ink = Color(hex: "171717")
        static let muted = Color(hex: "8b8b8b")
        static let border = Color.white.opacity(0.12)
        
        static let stateOk = Color(hex: "4f9f6e")
        static let stateWarn = Color(hex: "c79a42")
        static let stateError = Color(hex: "c95c5c")
        static let stateInfo = Color(hex: "6b8fbf")
        static let statePrivate = Color(hex: "8d78c8")
    }
}

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (1, 1, 1, 0)
        }

        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
