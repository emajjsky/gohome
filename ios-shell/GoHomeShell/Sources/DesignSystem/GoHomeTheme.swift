import SwiftUI
import UIKit

enum GoHomeTheme {
    static let paper = Color(red: 0.965, green: 0.961, blue: 0.945)
    static let surface = Color.white
    static let ink = Color(red: 0.09, green: 0.15, blue: 0.15)
    static let mutedInk = Color(red: 0.36, green: 0.42, blue: 0.41)
    static let line = Color(red: 0.09, green: 0.15, blue: 0.15).opacity(0.12)
    static let softLine = Color(red: 0.09, green: 0.15, blue: 0.15).opacity(0.07)
    static let ginger = Color(red: 0.78, green: 0.34, blue: 0.20)
    static let paleGinger = Color(red: 0.95, green: 0.87, blue: 0.81)
    static let leaf = Color(red: 0.16, green: 0.42, blue: 0.35)
    static let paleLeaf = Color(red: 0.85, green: 0.92, blue: 0.88)
    static let sky = Color(red: 0.84, green: 0.91, blue: 0.92)
    static let danger = Color(red: 0.72, green: 0.24, blue: 0.22)

    static let pageHorizontalPadding: CGFloat = 20
    static let compactRadius: CGFloat = 8
    static let controlRadius: CGFloat = 8
}

struct GoHomeLocalImage: View {
    let name: String
    var contentMode: ContentMode = .fill

    var body: some View {
        Group {
            if let image = GoHomeImageResource.loadJPEG(named: name) {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
            } else {
                GoHomeImagePlaceholder()
            }
        }
    }
}

enum GoHomeImageResource {
    static func loadJPEG(named name: String, bundle: Bundle = .main) -> UIImage? {
        guard let url = bundle.url(forResource: name, withExtension: "jpg") else { return nil }
        return UIImage(contentsOfFile: url.path)
    }
}

struct GoHomeImagePlaceholder: View {
    var body: some View {
        ZStack {
            GoHomeTheme.sky
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(GoHomeTheme.ink.opacity(0.55))
        }
    }
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
