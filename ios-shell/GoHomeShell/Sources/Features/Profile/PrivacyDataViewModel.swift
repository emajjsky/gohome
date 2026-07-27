import Foundation

@MainActor
final class PrivacyDataViewModel: ObservableObject {
    @Published private(set) var plan: AccountDeletionPlan?
    @Published private(set) var isLoading = false
    @Published private(set) var isExporting = false
    @Published private(set) var isDeleting = false
    @Published private(set) var exportURL: URL?
    @Published private(set) var errorMessage: String?

    private let repository: AppRepository?
    private var hasStarted = false

    init(repository: AppRepository?, seedPlan: AccountDeletionPlan? = nil) {
        self.repository = repository
        plan = seedPlan
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        if plan != nil { return }
        refreshPlan()
    }

    func refreshPlan() {
        guard let repository, !isLoading else { return }
        isLoading = true
        errorMessage = nil
        Task {
            defer { isLoading = false }
            do {
                plan = try await repository.accountDeletionPlan()
            } catch {
                errorMessage = "暂时无法读取账号状态"
            }
        }
    }

    func exportData() {
        guard let repository, !isExporting else { return }
        isExporting = true
        errorMessage = nil
        removeExportFile()
        Task {
            defer { isExporting = false }
            do {
                let data = try await repository.exportAccountData()
                let formatter = DateFormatter()
                formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.dateFormat = "yyyyMMdd-HHmmss"
                let url = FileManager.default.temporaryDirectory
                    .appendingPathComponent("Gohome-data-\(formatter.string(from: Date())).json")
                try data.write(to: url, options: [.atomic, .completeFileProtection])
                exportURL = url
            } catch {
                errorMessage = "数据导出失败，请稍后重试"
            }
        }
    }

    func deleteAccount() async -> Bool {
        guard let repository, plan?.canDelete == true, !isDeleting else { return false }
        isDeleting = true
        errorMessage = nil
        defer { isDeleting = false }
        do {
            try await repository.deleteAccount()
            return true
        } catch {
            errorMessage = "账号未能删除，请重新确认账号状态"
            refreshPlan()
            return false
        }
    }

    func clearExport() {
        removeExportFile()
    }

    private func removeExportFile() {
        if let exportURL {
            try? FileManager.default.removeItem(at: exportURL)
        }
        exportURL = nil
    }
}
