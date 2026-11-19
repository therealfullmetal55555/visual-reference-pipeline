import AppKit
import SwiftUI
import AVKit

enum DesktopPage: String, CaseIterable, Identifiable {
    case archive = "Архив"
    case board = "Доска"
    case collections = "Коллекции"
    case shots = "Шот-лист"
    case timeline = "Разбор видео"
    case comparison = "Сравнение"
    case search = "Визуальный поиск"
    case review = "Gemini"
    case editor = "Редактор"
    case collage = "Коллаж"

    var id: Self { self }
    var symbol: String {
        switch self {
        case .archive: return "photo.on.rectangle.angled"
        case .board: return "square.grid.2x2"
        case .collections: return "folder"
        case .shots: return "checklist"
        case .timeline: return "film"
        case .comparison: return "rectangle.split.2x1"
        case .search: return "magnifyingglass"
        case .review: return "sparkles"
        case .editor: return "slider.horizontal.3"
        case .collage: return "rectangle.grid.2x2"
        }
    }
}

@main
@MainActor
struct VisualReferenceApp: App {
    @StateObject private var store = DesktopStore()
    @AppStorage("appearance") private var appearance = "system"

    var body: some Scene {
        WindowGroup {
            Workspace(store: store)
                .frame(minWidth: 800, minHeight: 540)
                .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
        }
        .defaultSize(width: 1320, height: 840)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Импортировать файлы…") { store.importFiles() }.keyboardShortcut("o")
                Button("Выбрать папку архива…") { store.chooseArchive() }.keyboardShortcut("o", modifiers: [.command, .shift])
                Button("Показать папку данных") {
                    NSWorkspace.shared.activateFileViewerSelecting([DesktopEngine.dataDirectory])
                }
            }
        }
        Settings {
            Form {
                Picker("Оформление", selection: $appearance) {
                    Text("Как в системе").tag("system")
                    Text("Светлое").tag("light")
                    Text("Тёмное").tag("dark")
                }
            }.padding(24).frame(width: 340)
        }
    }
}

struct Workspace: View {
    @ObservedObject var store: DesktopStore
    @State private var page: DesktopPage? = .archive
    @State private var preview: NativeReference?
    @State private var videoSeed: String?
    @State private var exampleSeed: String?

    var body: some View {
        NavigationSplitView {
            List(selection: $page) {
                Section("Материалы") {
                    ForEach([DesktopPage.archive, .board, .collections]) { item in
                        Label(item.rawValue, systemImage: item.symbol).tag(item)
                    }
                }
                Section("Инструменты") {
                    ForEach([DesktopPage.shots, .timeline, .comparison, .search, .review, .editor, .collage]) { item in
                        Label(item.rawValue, systemImage: item.symbol).tag(item)
                    }
                }
            }
            .listStyle(.sidebar)
            .navigationTitle("Visual Reference")
            .navigationSplitViewColumnWidth(min: 180, ideal: 215)
        } detail: {
            Group {
                switch page ?? .archive {
                case .archive: ArchivePanel(store: store, preview: { preview = $0 }, openBoard: {
                    store.place(store.selected)
                    page = .board
                })
                case .board: BoardPanel(store: store, open: { preview = $0 })
                case .collections: CollectionsPanel(store: store, open: { preview = $0 })
                case .shots: ShotsPanel(store: store)
                case .timeline: TimelinePanel(store: store, initial: videoSeed)
                case .comparison: ComparePanel(store: store)
                case .search: SearchPanel(store: store, initial: exampleSeed, open: { preview = $0 })
                case .review: ReviewPanel(store: store)
                case .editor: PhotoEditor(store: store)
                case .collage: CollagePanel(store: store)
                }
            }
            .navigationTitle((page ?? .archive).rawValue)
            .toolbar {
                ToolbarItem { Button(action: store.importFiles) { Label("Импорт", systemImage: "plus") } }
                ToolbarItem { Button(action: store.chooseArchive) { Label("Папка архива", systemImage: "folder") } }
            }
        }
        .task { if store.items.isEmpty { store.withError { try await store.load() } } }
        .alert("Рабочая область", isPresented: Binding(get: { store.error != nil }, set: {
            if !$0 { store.error = nil }
        })) { Button("OK") { store.error = nil } } message: { Text(store.error ?? "") }
        .sheet(item: $preview) { ref in
            ReferencePreview(ref: ref, onBoard: {
                store.place([ref])
                preview = nil
                page = .board
            }, onRelated: {
                if ref.kind == "Видео" { videoSeed = ref.id; page = .timeline }
                else { exampleSeed = ref.id; page = .search }
                preview = nil
            })
        }
    }
}

struct NativeMedia: View {
    let reference: NativeReference
    var fit = false

    var body: some View {
        Group {
            if let image = nativeThumbnail(reference, size: fit ? 1600 : 480) {
                Image(nsImage: image).resizable()
                    .aspectRatio(contentMode: fit ? .fit : .fill)
            } else if reference.kind == "Видео" {
                Image(systemName: "play.rectangle").font(.system(size: 32)).foregroundStyle(.secondary)
            } else if reference.kind == "Аудио" {
                Image(systemName: "waveform").font(.system(size: 28)).foregroundStyle(.secondary)
            } else if let url = reference.url, !url.isFileURL {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().aspectRatio(contentMode: fit ? .fit : .fill) }
                    else { Image(systemName: "photo").foregroundStyle(.secondary) }
                }
            } else {
                Image(systemName: "photo").foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.quaternary)
        .clipped()
    }
}

struct ReferencePreview: View {
    let ref: NativeReference
    let onBoard: () -> Void
    let onRelated: () -> Void
    @State private var player = AVPlayer()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(ref.title).font(.title2.bold()).lineLimit(2)
                Spacer()
                Button("Закрыть") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            if ["Видео","Аудио"].contains(ref.kind), let url = ref.url {
                VideoPlayer(player: player).task { player.replaceCurrentItem(with: AVPlayerItem(url: url)) }
            } else if let url=ref.localURL, url.pathExtension.lowercased()=="gif" {
                NativeGIF(url:url)
            } else { NativeMedia(reference: ref, fit: true) }
            if !ref.notes.isEmpty { Text(ref.notes).foregroundStyle(.secondary) }
            HStack {
                Button("На доску", action: onBoard).disabled(ref.kind == "Аудио")
                Button(ref.kind == "Видео" ? "Разобрать видео" : "Найти похожие", action: onRelated)
                    .disabled(ref.localURL == nil || ref.kind == "Аудио")
                if let source = URL(string: ref.source), ["http","https"].contains(source.scheme ?? "") {
                    Link("Источник", destination: source)
                }
                if let url = ref.localURL {
                    Button("Показать в Finder") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
                }
            }
        }.padding(20).frame(width: 760, height: 580).onDisappear { player.pause() }
    }
}

struct NativeGIF: NSViewRepresentable {
    let url: URL
    func makeNSView(context: Context) -> NSImageView {
        let view=NSImageView()
        view.imageScaling = .scaleProportionallyUpOrDown
        view.animates=true
        view.image=NSImage(contentsOf:url)
        return view
    }
    func updateNSView(_ view: NSImageView,context: Context) {}
}

struct ArchivePanel: View {
    @ObservedObject var store: DesktopStore
    let preview: (NativeReference) -> Void
    let openBoard: () -> Void
    @State private var query = ""
    @State private var filter = "Все"
    @State private var selecting = false

    private var matches: [NativeReference] {
        store.items.filter { ref in
            let type = ref.preview.lowercased().contains(".gif") ? "GIF" : ref.kind
            return (filter == "Все" || type == filter)
                && (query.isEmpty || [ref.title,ref.tags,ref.notes].joined(separator: " ").localizedCaseInsensitiveContains(query))
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Picker("Тип", selection: $filter) {
                    ForEach(["Все","Фото","Видео","GIF","Аудио"],id:\.self) { Text($0).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(maxWidth: 370)
                Spacer()
                TextField("Поиск по архиву", text: $query).frame(width: 220)
                Toggle("Выбрать", isOn: $selecting).toggleStyle(.button)
                Button("На доску (\(store.selection.count))", action: openBoard)
                    .disabled(store.selection.isEmpty)
            }.padding([.top,.horizontal],16)
            if store.loading { ProgressView("Читаем архив…").padding() }
            if matches.isEmpty && !store.loading {
                Text("Нет подходящих материалов").foregroundStyle(.secondary).frame(maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 155, maximum: 260), spacing: 10)], spacing: 12) {
                        ForEach(matches) { ref in
                            Button {
                                if selecting || NSEvent.modifierFlags.contains(.command) { store.toggle(ref) }
                                else { preview(ref) }
                            } label: {
                                VStack(alignment: .leading, spacing: 5) {
                                    NativeMedia(reference: ref).aspectRatio(1, contentMode: .fit)
                                        .overlay(alignment: .topLeading) {
                                            if store.selection.contains(ref.id) {
                                                Image(systemName: "checkmark.circle.fill").padding(6)
                                                    .background(.regularMaterial, in: Circle()).padding(6)
                                            }
                                        }
                                    Text(ref.title).lineLimit(1).font(.caption)
                                }
                            }.buttonStyle(.plain).help(ref.title)
                        }
                    }.padding(.horizontal,16).padding(.bottom,16)
                }
            }
        }
    }
}

struct BoardPanel: View {
    @ObservedObject var store: DesktopStore
    let open: (NativeReference) -> Void

    private var contentBounds: CGRect {
        store.board.map(\.rect).reduce(CGRect.null) { $0.union($1) }.insetBy(dx: -22, dy: -22)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("\(store.board.count) материалов").foregroundStyle(.secondary)
                Spacer()
                Button("Источники") {
                    store.withError {
                        let text = store.board.map { "\($0.ref.title)\n\($0.ref.source)" }.joined(separator:"\n\n")
                        try nativeSave(Data(text.utf8), named:"moodboard-sources.txt")
                    }
                }.disabled(store.board.isEmpty)
                Button("Скачать PNG") {
                    store.withError {
                        try nativeSave(boardPNG(store.board), named: "moodboard.png")
                    }
                }.disabled(store.board.isEmpty)
            }.padding([.horizontal,.top],16)
            if store.board.isEmpty { Spacer(); Text("Выберите материалы в архиве и добавьте их на доску.").padding(); Spacer() }
            else {
                ScrollView([.horizontal,.vertical]) {
                    ZStack(alignment: .topLeading) {
                        ForEach(store.board) { item in
                            TileView(item: item, open: { open(item.ref) },
                                     move: { store.move(item.id, $0) }, remove: { store.remove(item.id) })
                                .position(x:item.rect.midX-contentBounds.minX, y:item.rect.midY-contentBounds.minY)
                        }
                    }
                    .frame(width: max(650,contentBounds.width), height: max(460,contentBounds.height))
                }.background(.quaternary)
            }
        }
    }
}

struct TileView: View {
    let item: NativeTile
    let open: () -> Void
    let move: (CGSize) -> Void
    let remove: () -> Void
    @GestureState private var drag = CGSize.zero

    var body: some View {
        NativeMedia(reference: item.ref)
            .frame(width:item.rect.width,height:item.rect.height)
            .overlay(alignment:.bottomLeading) {
                Text(item.ref.title).font(.caption).lineLimit(1)
                    .padding(5).background(.regularMaterial)
            }
            .contentShape(Rectangle())
            .offset(drag)
            .gesture(DragGesture().updating($drag) { value,state,_ in state=value.translation }
                .onEnded { move($0.translation) })
            .onTapGesture(count:2, perform:open)
            .contextMenu { Button("Открыть", action:open); Button("Убрать с доски", action:remove) }
    }
}

@MainActor
func boardPNG(_ tiles: [NativeTile]) throws -> Data {
    let bounds = tiles.map(\.rect).reduce(CGRect.null) { $0.union($1) }.insetBy(dx:-20,dy:-20)
    guard !bounds.isNull, !bounds.isEmpty else { throw DesktopError("Доска пуста.") }
    let scale = min(2,4096/max(bounds.width,bounds.height))
    let result = NSImage(size:NSSize(width:bounds.width*scale,height:bounds.height*scale), flipped:true) { surface in
        NSColor(white:0.10,alpha:1).setFill()
        surface.fill()
        for tile in tiles {
            let rect = CGRect(x:(tile.rect.minX-bounds.minX)*scale,y:(tile.rect.minY-bounds.minY)*scale,
                              width:tile.rect.width*scale,height:tile.rect.height*scale)
            if let image = nativeThumbnail(tile.ref,size:1300) {
                image.draw(in:rect, from:.zero, operation:.sourceOver, fraction:1, respectFlipped:true, hints:nil)
            } else {
                NSColor.darkGray.setFill()
                rect.fill()
                (tile.ref.title as NSString).draw(in:rect.insetBy(dx:6,dy:6),withAttributes:[.foregroundColor:NSColor.white])
            }
        }
        return true
    }
    return try imagePNG(result)
}

@MainActor
func imagePNG(_ image: NSImage) throws -> Data {
    guard let tiff=image.tiffRepresentation, let bitmap=NSBitmapImageRep(data:tiff),
          let png=bitmap.representation(using:.png,properties:[:]) else { throw DesktopError("Не удалось создать PNG.") }
    return png
}

struct CollectionsPanel: View {
    @ObservedObject var store: DesktopStore
    let open: (NativeReference) -> Void
    @State private var folder = ""
    @State private var name = ""

    private var members: [NativeReference] {
        let row = store.subscriptions.first { $0["id"] as? String == folder }
        let keys = Set(row?["items"] as? [String] ?? [])
        return store.items.filter { keys.contains(key($0)) }
    }

    private func key(_ ref: NativeReference) -> String { ref.archived ? "archive:"+ref.preview : "ref:"+ref.id }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Picker("Коллекция", selection:$folder) {
                    Text("Выбрать").tag("")
                    ForEach(store.subscriptions.indices,id:\.self) { index in
                        let row=store.subscriptions[index]
                        Text(row["name"] as? String ?? "").tag(row["id"] as? String ?? "")
                    }
                }
                TextField("Новая коллекция",text:$name)
                Button("Создать") {
                    store.withError {
                        let body=try await store.api("/api/folders","POST",body:["name":name]) as? [String:Any]
                        try await store.loadCollections()
                        folder=body?["id"] as? String ?? ""
                        name=""
                    }
                }.disabled(name.trimmingCharacters(in:.whitespaces).isEmpty)
                Button("Добавить выделение") {
                    store.withError {
                        for ref in store.selected {
                            _ = try await store.api("/api/folders/"+folder+"/items","PUT",body:["key":key(ref),"present":true])
                        }
                        try await store.loadCollections()
                    }
                }.disabled(folder.isEmpty || store.selection.isEmpty)
            }
            List(members) { reference in
                HStack {
                    NativeMedia(reference:reference).frame(width:54,height:45)
                    Text(reference.title)
                    Spacer()
                    Button("Открыть") { open(reference) }
                    Button("Убрать") {
                        store.withError {
                            _ = try await store.api("/api/folders/"+folder+"/items","PUT",body:["key":key(reference),"present":false])
                            try await store.loadCollections()
                        }
                    }
                }
            }
        }.padding(16)
    }
}
