// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "IntakeConsole",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "IntakeConsole", targets: ["IntakeConsole"])
    ],
    targets: [
        .executableTarget(
            name: "IntakeConsole",
            dependencies: []),
        .testTarget(
            name: "IntakeConsoleTests",
            dependencies: ["IntakeConsole"]),
    ]
)
