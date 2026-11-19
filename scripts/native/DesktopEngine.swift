import AppKit
import Darwin
import Foundation
import SwiftUI
import ImageIO
import UniformTypeIdentifiers

struct DesktopError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

final class DesktopEngine: @unchecked Sendable {
    private let queue = DispatchQueue(label: "visual-reference.local-engine")
    private var process: Process?
    private var writer: FileHandle?
    private var reader: FileHandle?
    private var buffered = Data()
    private let workerScript: URL?

    init(workerScript: URL? = nil) { self.workerScript = workerScript }
    static let dataDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Visual Reference Workflow", isDirectory: true)

    func call(_ request: [String: Any], archive: String, restart: Bool = false) async throws -> Any {
        try await withCheckedThrowingContinuation { continuation in
            queue.async {
                do {
                    if restart { self.stop() }
                    if self.process?.isRunning != true { try self.start(archive: archive) }
                    guard let writer = self.writer, let reader = self.reader else {
                        throw DesktopError("Внутренний процесс не запущен.")
                    }
                    var line = try JSONSerialization.data(withJSONObject: request)
                    line.append(10)
                    let response: Any
                    do {
                        try writer.write(contentsOf: line)
                        response = try self.readReply(from: reader)
                    } catch {
                        self.stop()
                        throw error
                    }
                    guard let object = response as? [String: Any], object["ok"] as? Bool == true else {
                        throw DesktopError((response as? [String: Any])?["error"] as? String ?? "Ошибка рабочего процесса.")
                    }
                    continuation.resume(returning: object["result"] ?? NSNull())
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func readReply(from handle: FileHandle) throws -> Any {
        let deadline = DispatchTime.now().uptimeNanoseconds + 125_000_000_000
        var chunk = [UInt8](repeating: 0, count: 32_768)
        while true {
            if let newline = buffered.firstIndex(of: 10) {
                let line = Data(buffered[..<newline])
                buffered.removeSubrange(...newline)
                return try JSONSerialization.jsonObject(with: line)
            }
            let now = DispatchTime.now().uptimeNanoseconds
            guard now < deadline else {
                throw DesktopError("Движок не ответил. Повторите загрузку или проверьте доступ к папке архива.")
            }
            guard buffered.count < 32 * 1024 * 1024 else {
                throw DesktopError("Слишком большой ответ при чтении архива.")
            }
            var descriptor = pollfd(fd: handle.fileDescriptor, events: Int16(POLLIN), revents: 0)
            let ready = Darwin.poll(&descriptor, 1, Int32((deadline - now + 999_999) / 1_000_000))
            if ready < 0 && errno == EINTR { continue }
            if ready == 0 {
                throw DesktopError("Движок не ответил. Повторите загрузку или проверьте доступ к папке архива.")
            }
            if ready < 0 || (descriptor.revents & Int16(POLLIN)) == 0 {
                throw DesktopError("Движок закрыл соединение. Проверьте Python и доступ к папке данных.")
            }
            let count = chunk.withUnsafeMutableBytes { Darwin.read(handle.fileDescriptor, $0.baseAddress, $0.count) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { throw DesktopError("Движок завершился во время загрузки.") }
            buffered.append(contentsOf: chunk.prefix(count))
        }
    }

    private func start(archive: String) throws {
        stop()
        let env = ProcessInfo.processInfo.environment
        guard let script = workerScript ?? Bundle.main.url(forResource: "desktop_bootstrap", withExtension: "py", subdirectory: "app") else {
            throw DesktopError("В сборке отсутствует движок обработки.")
        }
        let embedded = Bundle.main.resourceURL?.appendingPathComponent("python/bin/python3").path
        let paths = [env["VRW_PYTHON"], embedded, "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        guard let python = paths.compactMap({ $0 }).first(where: FileManager.default.isExecutableFile(atPath:)) else {
            throw DesktopError("Для обработки архива требуется Python 3.9 или новее.")
        }
        let child = Process()
        let input = Pipe()
        let output = Pipe()
        child.executableURL = URL(fileURLWithPath: python)
        child.arguments = ["-u", script.path]
        child.standardInput = input
        child.standardOutput = output
        var options = env
        options["REFERENCE_DATA_DIR"] = env["REFERENCE_DATA_DIR"] ?? Self.dataDirectory.path
        options["REFERENCE_ARCHIVE_DIR"] = archive.isEmpty ? nil : archive
        let previous = env["REFERENCE_PREVIOUS_WORKSPACE"]
            ?? Bundle.main.object(forInfoDictionaryKey: "VRWPreviousWorkspace") as? String
        let legacy = archive.isEmpty ? nil : URL(fileURLWithPath:archive).appendingPathComponent("reference_app").path
        options["REFERENCE_PREVIOUS_WORKSPACE"] = [previous,legacy].compactMap { $0 }.first {
            FileManager.default.fileExists(atPath: URL(fileURLWithPath:$0).appendingPathComponent("references.sqlite3").path)
        }
        options["PYTHONDONTWRITEBYTECODE"] = "1"
        options["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
        child.environment = options
        try child.run()
        process = child
        writer = input.fileHandleForWriting
        reader = output.fileHandleForReading
    }

    private func stop() {
        try? writer?.close()
        try? reader?.close()
        if process?.isRunning == true { process?.terminate() }
        writer = nil
        reader = nil
        process = nil
        buffered.removeAll()
    }

    deinit { stop() }
}

struct NativeReference: Identifiable, Hashable {
    let id: String
    let title: String
    let source: String
    let preview: String
    let path: String
    let kind: String
    let tags: String
    let notes: String
    let archived: Bool

    init(_ data: [String: Any]) {
        preview = data["preview"] as? String ?? data["src"] as? String ?? ""
        id = data["id"] as? String ?? preview
        title = data["title"] as? String ?? "Без названия"
        source = data["url"] as? String ?? data["sourceUrl"] as? String ?? ""
        path = data["filePath"] as? String ?? ""
        kind = data["type"] as? String ?? (data["kind"] as? String == "video" ? "Видео" : "Фото")
        tags = data["tags"] as? String ?? ""
        notes = data["description"] as? String ?? ""
        archived = data["archived"] as? Bool ?? false
    }

    var localURL: URL? { path.isEmpty ? nil : URL(fileURLWithPath: path) }
    var url: URL? {
        if let localURL { return localURL }
        guard let url = URL(string: preview), ["https","http"].contains(url.scheme ?? "") else { return nil }
        return url
    }

    var record: [String: Any] { ["id":id,"title":title,"url":source,"preview":preview,"type":kind] }
}

struct NativeTile: Identifiable {
    var raw: [String: Any]
    var id: String { raw["id"] as? String ?? "" }
    var ref: NativeReference { NativeReference(raw) }
    var rect: CGRect {
        CGRect(x: raw["x"] as? Double ?? 0, y: raw["y"] as? Double ?? 0,
               width: max(1, raw["w"] as? Double ?? 200), height: max(1, raw["h"] as? Double ?? 180))
    }
}

@MainActor
final class DesktopStore: ObservableObject {
    @Published var items: [NativeReference] = []
    @Published var selection: Set<String> = []
    @Published var board: [NativeTile] = []
    @Published var error: String?
    @Published var loading = false
    @Published var loadIssue: String?
    @Published var subscriptions: [[String: Any]] = []
    private let engine = DesktopEngine()
    private var archive: String
    private var boardWrite: Task<Void, Never>?

    init() {
        archive = UserDefaults.standard.string(forKey: "archiveDirectory")
            ?? ProcessInfo.processInfo.environment["REFERENCE_ARCHIVE_DIR"]
            ?? Bundle.main.object(forInfoDictionaryKey: "VRWInitialArchive") as? String ?? ""
    }

    var selected: [NativeReference] { items.filter { selection.contains($0.id) } }
    var videos: [NativeReference] { items.filter { $0.kind == "Видео" && $0.localURL != nil } }
    var photos: [NativeReference] { items.filter { $0.kind == "Фото" || $0.kind == "Карусель" } }

    func call(_ operation: [String: Any], restart: Bool = false) async throws -> Any {
        try await engine.call(operation, archive: archive, restart: restart)
    }

    func api(_ path: String, _ method: String = "GET", body: Any? = nil) async throws -> Any {
        var command: [String: Any] = ["op":"api", "path":path, "method":method]
        if let body { command["body"] = body }
        return try await call(command)
    }

    func withError(_ operation: @escaping () async throws -> Void) {
        Task {
            do { try await operation() }
            catch { self.error = error.localizedDescription }
        }
    }

    func reload() async {
        do { try await load() }
        catch { loadIssue = error.localizedDescription }
    }

    func load(archive changed: URL? = nil) async throws {
        guard !loading else { return }
        loadIssue = nil
        if let changed {
            archive = changed.path
            UserDefaults.standard.set(archive, forKey: "archiveDirectory")
            selection.removeAll()
        }
        loading = true
        defer { loading = false }
        let data = try await call(["op":"catalog"], restart: changed != nil)
        items = (data as? [[String: Any]] ?? []).map(NativeReference.init)
        let layout = try await call(["op":"board"])
        board = (layout as? [[String: Any]] ?? []).map(NativeTile.init)
        try await loadCollections()
    }

    func loadCollections() async throws {
        subscriptions = try await api("/api/folders") as? [[String: Any]] ?? []
    }

    func chooseArchive() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.directoryURL = archive.isEmpty ? nil : URL(fileURLWithPath: archive)
        panel.message = "Выберите папку архива с images, videos или archive_index.json."
        guard panel.runModal() == .OK, let folder = panel.url else { return }
        guard ["images", "videos", "archive_index.json"].contains(where: {
            FileManager.default.fileExists(atPath: folder.appendingPathComponent($0).path)
        }) else {
            error = "Выберите папку архива."
            return
        }
        Task {
            do { try await load(archive: folder) }
            catch { loadIssue = error.localizedDescription }
        }
    }

    func importItem(_ file: URL, title: String = "", source: String = "", notes: String = "") async throws -> NativeReference {
        let result = try await call(["op":"import","file":file.path,"title":title,"source":source,"description":notes])
        guard let data = result as? [String: Any] else { throw DesktopError("Не удалось добавить файл.") }
        let imported = NativeReference(data)
        items.insert(imported, at: 0)
        return imported
    }

    func importFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.image, .movie, .mp3]
        guard panel.runModal() == .OK else { return }
        withError {
            for file in panel.urls { _ = try await self.importItem(file) }
        }
    }

    func toggle(_ reference: NativeReference) {
        if !selection.insert(reference.id).inserted { selection.remove(reference.id) }
    }

    func place(_ references: [NativeReference]) {
        let refs = references.filter { $0.url != nil && $0.kind != "Аудио" }
        guard !refs.isEmpty else { return }
        guard board.count + refs.count <= 1000 else { error = "На доске помещается до 1000 элементов."; return }
        let y = (board.map { $0.rect.maxY }.max() ?? -22) + 22
        for (index, ref) in refs.enumerated() {
            let image = nativeThumbnail(ref, size: 700)
            let height = min(320, max(90, 215 * (image?.size.height ?? 160) / max(1, image?.size.width ?? 215)))
            board.append(NativeTile(raw: ["id":UUID().uuidString,"src":ref.preview,"filePath":ref.path,
                "title":ref.title,"sourceUrl":ref.source,"kind":ref.kind=="Видео" ? "video":"image",
                "x":Double((index%4)*239),"y":y+Double(index/4)*344,"w":215.0,"h":height]))
        }
        saveBoard()
    }

    func move(_ id: String, _ offset: CGSize) {
        guard let i = board.firstIndex(where: { $0.id == id }) else { return }
        let rect = board[i].rect
        board[i].raw["x"] = rect.minX + offset.width
        board[i].raw["y"] = rect.minY + offset.height
        saveBoard()
    }

    func remove(_ id: String) {
        board.removeAll { $0.id == id }
        saveBoard()
    }

    private func saveBoard() {
        let layout = board.map { tile in
            tile.raw.filter { !["filePath", "preview"].contains($0.key) }
        }
        let previous = boardWrite
        boardWrite = Task {
            await previous?.value
            do { _ = try await api("/api/board","PUT",body:layout) }
            catch { self.error = error.localizedDescription }
        }
    }

    func changeDocument(_ name: String, _ update: (inout [[String: Any]]) -> Void) async throws -> [[String: Any]] {
        let route = "/api/workflow/" + name
        guard let data = try await api(route) as? [String: Any], let revision = data["revision"] as? String else {
            throw DesktopError("Не удалось открыть сохранённые данные.")
        }
        var rows = data["items"] as? [[String: Any]] ?? []
        update(&rows)
        let result = try await api(route,"PUT",body:["items":rows,"revision":revision]) as? [String: Any]
        return result?["items"] as? [[String: Any]] ?? rows
    }

    func document(_ name: String) async throws -> [[String: Any]] {
        let result = try await api("/api/workflow/"+name) as? [String: Any]
        return result?["items"] as? [[String: Any]] ?? []
    }
}

private let thumbnailCache: NSCache<NSString, NSImage> = {
    let cache = NSCache<NSString, NSImage>()
    cache.countLimit = 360
    return cache
}()

func nativeThumbnail(_ ref: NativeReference, size: Int = 480) -> NSImage? {
    guard ref.kind != "Видео", let url = ref.localURL else { return nil }
    let key = (url.path + "#" + String(size)) as NSString
    if let cached = thumbnailCache.object(forKey:key) { return cached }
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways:true,
            kCGImageSourceCreateThumbnailWithTransform:true,
            kCGImageSourceThumbnailMaxPixelSize:size
          ] as CFDictionary) else { return nil }
    let rendered = NSImage(cgImage: image, size: NSSize(width: image.width,height:image.height))
    thumbnailCache.setObject(rendered,forKey:key)
    return rendered
}

@MainActor
func nativeSave(_ data: Data, named filename: String) throws {
    let panel = NSSavePanel()
    panel.nameFieldStringValue = filename
    guard panel.runModal() == .OK, let url = panel.url else { return }
    try data.write(to: url, options: .atomic)
}
