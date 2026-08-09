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
    private var planTask: Task<Void, Never>?
    private var exportTask: Task<Void, Never>?
    private var planGeneration = 0
    private var exportGeneration = 0
    private var deletionGeneration = 0
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
        planTask?.cancel()
        planGeneration += 1
        let generation = planGeneration
        isLoading = true
        errorMessage = nil
        let task = Task { @MainActor [weak self, repository, generation] in
            defer {
                if let self, self.planGeneration == generation {
                    self.isLoading = false
                    self.planTask = nil
                }
            }
            do {
                let nextPlan = try await repository.accountDeletionPlan()
                try Task.checkCancellation()
                guard let self, self.planGeneration == generation else { return }
                self.plan = nextPlan
            } catch is CancellationError {
                return
            } catch {
                guard let self, self.planGeneration == generation else { return }
                self.errorMessage = "暂时无法读取账号状态"
            }
        }
        planTask = task
    }

    func exportData() {
        guard let repository, !isExporting else { return }
        exportTask?.cancel()
        exportGeneration += 1
        let generation = exportGeneration
        isExporting = true
        errorMessage = nil
        removeExportFile()
        let task = Task { @MainActor [weak self, repository, generation] in
            var generatedURL: URL?
            defer {
                if let self, self.exportGeneration == generation {
                    self.isExporting = false
                    self.exportTask = nil
                }
            }
            do {
                let data = try await repository.exportAccountData()
                try Task.checkCancellation()
                let formatter = DateFormatter()
                formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.dateFormat = "yyyyMMdd-HHmmss"
                let url = FileManager.default.temporaryDirectory
                    .appendingPathComponent("Gohome-data-\(formatter.string(from: Date())).json")
                try data.write(to: url, options: [.atomic, .completeFileProtection])
                generatedURL = url
                try Task.checkCancellation()
                guard let self, self.exportGeneration == generation else {
                    try? FileManager.default.removeItem(at: url)
                    return
                }
                self.exportURL = url
            } catch is CancellationError {
                if let generatedURL {
                    try? FileManager.default.removeItem(at: generatedURL)
                }
                return
            } catch {
                if let generatedURL {
                    try? FileManager.default.removeItem(at: generatedURL)
                }
                guard let self, self.exportGeneration == generation else { return }
                self.errorMessage = "数据导出失败，请稍后重试"
            }
        }
        exportTask = task
    }

    func deleteAccount() async -> Bool {
        guard let repository, plan?.canDelete == true, !isDeleting else { return false }
        deletionGeneration += 1
        let generation = deletionGeneration
        isDeleting = true
        errorMessage = nil
        defer {
            if deletionGeneration == generation {
                isDeleting = false
            }
        }
        do {
            try await repository.deleteAccount()
            try Task.checkCancellation()
            guard deletionGeneration == generation else { return false }
            return true
        } catch {
            if Task.isCancelled || deletionGeneration != generation { return false }
            errorMessage = "账号未能删除，请重新确认账号状态"
            refreshPlan()
            return false
        }
    }

    func cancelInFlightTasks() {
        planGeneration += 1
        exportGeneration += 1
        deletionGeneration += 1
        planTask?.cancel()
        exportTask?.cancel()
        planTask = nil
        exportTask = nil
        isLoading = false
        isExporting = false
        isDeleting = false
        removeExportFile()
    }

    func clearExport() {
        exportGeneration += 1
        exportTask?.cancel()
        exportTask = nil
        isExporting = false
        removeExportFile()
    }

    private func removeExportFile() {
        if let exportURL {
            try? FileManager.default.removeItem(at: exportURL)
        }
        exportURL = nil
    }

    deinit {
        planTask?.cancel()
        exportTask?.cancel()
    }
}
