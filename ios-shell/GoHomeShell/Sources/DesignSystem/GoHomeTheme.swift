import SwiftUI

enum GoHomeTheme {
    static let paper = Color.white
    static let ink = Color(red: 0.09, green: 0.09, blue: 0.08)
    static let mutedInk = Color(red: 0.42, green: 0.41, blue: 0.38)
    static let line = Color.black.opacity(0.10)
    static let softLine = Color.black.opacity(0.06)
    static let ginger = Color(red: 0.86, green: 0.62, blue: 0.18)
    static let paleGinger = Color(red: 0.98, green: 0.92, blue: 0.77)

    static let pageHorizontalPadding: CGFloat = 20
    static let compactRadius: CGFloat = 8
    static let controlRadius: CGFloat = 8
}

enum GoHomeTab: Hashable {
    case home
    case guardView
    case memory
    case community
    case profile

    var title: String {
        switch self {
        case .home: return "首页"
        case .guardView: return "守护"
        case .memory: return "记忆"
        case .community: return "社区"
        case .profile: return "我的"
        }
    }

    var icon: String {
        switch self {
        case .home: return "house"
        case .guardView: return "viewfinder"
        case .memory: return "photo.on.rectangle.angled"
        case .community: return "square.grid.2x2"
        case .profile: return "person"
        }
    }
}
