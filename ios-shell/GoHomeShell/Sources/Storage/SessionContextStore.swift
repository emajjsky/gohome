import Foundation

actor SessionContextStore {
    private struct Snapshot: Codable {
        let userID: String
        let familyID: String
    }

    private let defaults: UserDefaults
    private let key: String

    init(defaults: UserDefaults = .standard, key: String = "gohome.native.session-context") {
        self.defaults = defaults
        self.key = key
    }

    func scope() -> CacheScope? {
        guard
            let data = defaults.data(forKey: key),
            let snapshot = try? JSONDecoder().decode(Snapshot.self, from: data),
            !snapshot.userID.isEmpty,
            !snapshot.familyID.isEmpty
        else { return nil }
        return CacheScope(userID: snapshot.userID, familyID: snapshot.familyID)
    }

    func save(scope: CacheScope) {
        let snapshot = Snapshot(userID: scope.userID, familyID: scope.familyID)
        defaults.set(try? JSONEncoder().encode(snapshot), forKey: key)
    }

    func clear() {
        defaults.removeObject(forKey: key)
    }
}
