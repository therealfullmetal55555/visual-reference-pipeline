import AppKit
import Combine
import AVKit
import SwiftUI

struct ShotsPanel: View {
    @ObservedObject var store: DesktopStore
    @State private var rows: [[String: Any]] = []
    @State private var focused = ""
    @State private var title = ""
    @State private var notes = ""
    @State private var onSet = false

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Button("С доски") { add(store.board.map(\.ref)) }.disabled(store.board.isEmpty)
                Button("Из выделения") { add(store.selected) }.disabled(store.selected.isEmpty)
                Button("Новый кадр") { add([]) }
                Spacer()
                Toggle("На площадке",isOn:$onSet).toggleStyle(.button)
                Button("Скачать") {
                    store.withError {
                        let text=rows.enumerated().map { index,row in
                            let done=row["done"] as? Bool == true ? "x" : " "
                            return "\(index+1). [\(done)] \(row["title"] as? String ?? "")\n\(row["note"] as? String ?? "")\n\(row["url"] as? String ?? "")"
                        }.joined(separator:"\n\n")
                        try nativeSave(Data(text.utf8),named:"shot-list.txt")
                    }
                }.disabled(rows.isEmpty)
            }
            List {
                ForEach(rows.indices,id:\.self) { index in
                    let row=rows[index]
                    let id=row["id"] as? String ?? ""
                    HStack {
                        Text("\(index+1)").monospacedDigit().foregroundStyle(.secondary).frame(width:22)
                        Toggle("Снято",isOn:Binding(get:{ row["done"] as? Bool ?? false },set:{ value in
                            modify { drafts in
                                if let i=drafts.firstIndex(where:{$0["id"] as? String == id}) { drafts[i]["done"]=value }
                            }
                        }))
                        VStack(alignment:.leading) {
                            Text(row["title"] as? String ?? "").font(.headline)
                            Text(row["note"] as? String ?? "").foregroundStyle(.secondary)
                        }
                        Spacer()
                        if !onSet {
                            Group {
                                Button("↑") { move(id,-1) }.disabled(index==0)
                                Button("↓") { move(id,1) }.disabled(index==rows.count-1)
                                Button("Править") {
                                    focused=id
                                    title=row["title"] as? String ?? ""
                                    notes=row["note"] as? String ?? ""
                                }
                                Button("Убрать") {
                                    modify { $0.removeAll { $0["id"] as? String == id } }
                                    if focused == id { focused="" }
                                }
                            }.buttonStyle(.borderless)
                        }
                    }
                }
            }
            if !focused.isEmpty && !onSet {
                TextField("Название кадра",text:$title)
                TextField("Свет, крупность, поза или движение",text:$notes,axis:.vertical).lineLimit(2...4)
                Button("Сохранить") {
                    let id=focused, shotTitle=title, shotNotes=notes
                    modify {
                        if let i=$0.firstIndex(where:{$0["id"] as? String == id}) {
                            $0[i]["title"]=shotTitle
                            $0[i]["note"]=shotNotes
                        }
                    }
                    focused=""
                }.buttonStyle(.borderedProminent)
            }
        }.padding(16).task { store.withError { rows=try await store.document("shots") } }
    }

    private func add(_ references: [NativeReference]) {
        if references.isEmpty {
            let id=UUID().uuidString
            modify { $0.append(["id":id,"title":"Новый кадр","note":"","done":false]) }
            focused=id
            title=""
            notes=""
            return
        }
        modify { rows in
            var existing=Set(rows.compactMap { $0["preview"] as? String })
            for ref in references where existing.insert(ref.preview).inserted {
                rows.append(["id":UUID().uuidString,"title":ref.title,"preview":ref.preview,"url":ref.source,"note":"","done":false])
            }
        }
    }

    private func move(_ id: String,_ delta: Int) {
        modify {
            guard let current=$0.firstIndex(where:{$0["id"] as? String == id}), $0.indices.contains(current+delta) else { return }
            $0.swapAt(current,current+delta)
        }
    }

    private func modify(_ operation: @escaping (inout [[String:Any]]) -> Void) {
        store.withError { rows=try await store.changeDocument("shots",operation) }
    }
}

func timecode(_ seconds: Double) -> String {
    let ms=Int((seconds.isFinite ? max(0,seconds) : 0)*1000)
    return String(format:"%02d:%02d.%03d",ms/60000,(ms/1000)%60,ms%1000)
}

struct TimelinePanel: View {
    @ObservedObject var store: DesktopStore
    let initial: String?
    @State private var selectedID = ""
    @State private var player = AVPlayer()
    @State private var time = 0.0
    @State private var marker = ""
    @State private var marks: [[String:Any]] = []
    @State private var start = 0.0
    @State private var end = 0.0
    @State private var working = false
    @State private var feedback = ""
    private let timer=Timer.publish(every:0.15,on:.main,in:.common).autoconnect()

    private var source: NativeReference? { store.videos.first { $0.id == selectedID } }
    private var currentMarks: [[String:Any]] {
        guard let source else { return [] }
        return marks.filter { $0["preview"] as? String == source.preview }
            .sorted { ($0["time"] as? Double ?? 0) < ($1["time"] as? Double ?? 0) }
    }

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Picker("Видео",selection:$selectedID) {
                    Text("Выбрать").tag("")
                    ForEach(store.videos) { Text($0.title).tag($0.id) }
                }
                Button("Импортировать…",action:store.importFiles)
            }
            VideoPlayer(player:player).frame(minHeight:200,idealHeight:330,maxHeight:400)
            HStack {
                Text(timecode(time)).monospacedDigit()
                TextField("Заметка о склейке",text:$marker)
                Button("Поставить метку") { addMarker() }.disabled(source == nil || working)
                Button("Кадр в архив") { capture(false) }.disabled(source == nil || working)
                Button("Кадр на доску") { capture(true) }.disabled(source == nil || working)
            }
            HStack {
                Button("Начало \(timecode(start))") { start=time }
                Button("Конец \(timecode(end))") { end=time }
                Button("Сохранить MP4") { exportClip() }.disabled(source == nil || working || end-start < 0.1 || end-start>60)
                Spacer()
                Button("Скачать схему") { exportMarkers() }.disabled(currentMarks.isEmpty)
            }
            List {
                ForEach(currentMarks.indices,id:\.self) { index in
                    let row=currentMarks[index], position=row["time"] as? Double ?? 0
                    HStack {
                        Button(timecode(position)) {
                            player.seek(to:CMTime(seconds:position,preferredTimescale:1000),toleranceBefore:.zero,toleranceAfter:.zero)
                        }.buttonStyle(.borderless)
                        Text(row["note"] as? String ?? "")
                        Spacer()
                        Button("Убрать") {
                            let id=row["id"] as? String
                            store.withError {
                                marks=try await store.changeDocument("timeline") { drafts in
                                    drafts.removeAll { $0["id"] as? String == id }
                                }
                            }
                        }.buttonStyle(.borderless)
                    }
                }
            }
            if working { ProgressView().scaleEffect(0.7) }
            if !feedback.isEmpty { Text(feedback).foregroundStyle(.secondary) }
        }.padding(16)
            .task {
                selectedID=initial ?? store.videos.first?.id ?? ""
                store.withError { marks=try await store.document("timeline") }
            }
            .onChange(of:selectedID) { _ in
                player.pause()
                player.replaceCurrentItem(with:source?.localURL.map(AVPlayerItem.init(url:)))
                start=0;end=0;time=0
            }
            .onReceive(timer) { _ in
                let value=player.currentTime().seconds
                if value.isFinite { time=value }
            }
            .onDisappear { player.pause() }
    }

    private func addMarker() {
        guard let source else { return }
        let position=time
        let note=marker.isEmpty ? "Склейка" : marker
        store.withError {
            marks=try await store.changeDocument("timeline") {
                $0.append(["id":UUID().uuidString,"preview":source.preview,"time":position,"note":note])
            }
            marker=""
        }
    }

    private func capture(_ toBoard: Bool) {
        guard let source, let url=source.localURL else { return }
        let position=time, note=marker
        run {
            let caption="\(source.title) · \(timecode(position))"
            let image=try await stillFrame(url,at:position)
            let temp=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".png")
            defer { try? FileManager.default.removeItem(at:temp) }
            try image.write(to:temp,options:.atomic)
            let saved=try await store.importItem(temp,title:caption,source:source.source,notes:[caption,note].filter{ !$0.isEmpty }.joined(separator:"\n"))
            if toBoard { store.place([saved]) }
            feedback=toBoard ? "Кадр сохранён и добавлен на доску." : "Кадр сохранён в архив."
        }
    }

    private func exportClip() {
        guard let source else { return }
        let from=start, to=end
        run {
            let title=source.title+" · "+timecode(from)+"–"+timecode(to)
            let response=try await store.call(["op":"clip","title":title,"source":source.source,
                                               "body":["preview":source.preview,"start":from,"end":to]]) as? [String:Any]
            guard let response, let file=response["filePath"] as? String, !file.isEmpty else {
                throw DesktopError("Фрагмент не сохранился.")
            }
            store.items.insert(NativeReference(response),at:0)
            try nativeSave(Data(contentsOf:URL(fileURLWithPath:file),options:.mappedIfSafe),named:"clip.mp4")
            feedback="Фрагмент сохранён в архив."
        }
    }

    private func exportMarkers() {
        store.withError {
            let lines=currentMarks.map { "\(timecode($0["time"] as? Double ?? 0))  \($0["note"] as? String ?? "")" }
            try nativeSave(Data(lines.joined(separator:"\n").utf8),named:"video-breakdown.txt")
        }
    }

    private func run(_ action: @escaping () async throws -> Void) {
        working=true
        feedback=""
        store.withError {
            defer { working=false }
            try await action()
        }
    }
}

@MainActor
private func stillFrame(_ url: URL, at seconds: Double) async throws -> Data {
    let image: CGImage = try await withCheckedThrowingContinuation { continuation in
        DispatchQueue.global(qos:.userInitiated).async {
            let generator=AVAssetImageGenerator(asset:AVURLAsset(url:url))
            generator.appliesPreferredTrackTransform=true
            generator.maximumSize=CGSize(width:1920,height:1920)
            generator.requestedTimeToleranceBefore = CMTime(value:1,timescale:120)
            generator.requestedTimeToleranceAfter = CMTime(value:1,timescale:120)
            do {
                let frame=try generator.copyCGImage(at:CMTime(seconds:seconds,preferredTimescale:1000),actualTime:nil)
                continuation.resume(returning:frame)
            } catch { continuation.resume(throwing:error) }
        }
    }
    return try imagePNG(NSImage(cgImage:image,size:NSSize(width:image.width,height:image.height)))
}

struct ComparePanel: View {
    @ObservedObject var store: DesktopStore
    @State private var left = ""
    @State private var right = ""
    @State private var note = ""
    @State private var zoom = 1.0
    @State private var horizontal = 0.0
    @State private var vertical = 0.0
    @State private var wipe = 0.5
    @State private var overlay = false
    @State private var saved = ""
    @State private var records: [[String:Any]] = []

    private var photos: [NativeReference] { store.photos.filter { $0.localURL != nil } }
    private var pair: (NativeReference?,NativeReference?) {
        (photos.first { $0.preview==left }, photos.first { $0.preview==right })
    }

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                choose("Исходник",selection:$left)
                choose("Референс",selection:$right)
                Toggle("Шторка",isOn:$overlay).toggleStyle(.button)
            }
            plate.frame(minHeight:260,idealHeight:380,maxHeight:450).background(.quaternary)
            HStack {
                Slider(value:$zoom,in:1...3) { Text("Масштаб") }
                Slider(value:$horizontal,in:-0.5...0.5) { Text("Сдвиг X") }
                Slider(value:$vertical,in:-0.5...0.5) { Text("Сдвиг Y") }
                if overlay { Slider(value:$wipe,in:0...1) { Text("Шторка") } }
            }
            TextField("Правки по цвету и кадрированию",text:$note,axis:.vertical).lineLimit(2...4)
            HStack {
                Picker("Сохранённые",selection:$saved) {
                    Text("Выбрать").tag("")
                    ForEach(records.indices,id:\.self) { index in
                        let row=records[index]
                        Text(row["title"] as? String ?? "").tag(row["id"] as? String ?? "")
                    }
                }.onChange(of:saved) { _ in restore() }
                Spacer()
                Button("Сохранить") { persist() }.disabled(pair.0 == nil || pair.1 == nil)
                Button("Скачать заметку") {
                    store.withError { try nativeSave(Data(note.utf8),named:"comparison-notes.txt") }
                }.disabled(note.isEmpty)
                Button("Скачать PNG") {
                    store.withError {
                        let renderer=ImageRenderer(content:plate.frame(width:1200,height:640))
                        guard let image=renderer.nsImage else { throw DesktopError("Не удалось собрать сравнение.") }
                        try nativeSave(imagePNG(image),named:"comparison.png")
                    }
                }.disabled(pair.0 == nil || pair.1 == nil)
            }
            Spacer(minLength:0)
        }.padding(16).task {
            let selection=store.selected.filter { $0.kind=="Фото" && $0.localURL != nil }
            left=selection.first?.preview ?? ""
            right=selection.dropFirst().first?.preview ?? ""
            store.withError { records=try await store.document("comparisons") }
        }
    }

    @ViewBuilder private var plate: some View {
        if overlay {
            GeometryReader { geometry in
                ZStack(alignment:.leading) {
                    image(pair.0, shifted: true)
                    image(pair.1, shifted: false).mask(alignment:.leading) {
                        Rectangle().frame(width:geometry.size.width*wipe)
                    }
                }.clipped()
            }
        } else { HStack(spacing:8) { image(pair.0,shifted:true); image(pair.1,shifted:false) } }
    }

    private func image(_ reference: NativeReference?, shifted: Bool) -> some View {
        GeometryReader { geometry in
            ZStack {
                Color(nsColor:.windowBackgroundColor)
                if let reference {
                    NativeMedia(reference:reference,fit:true).scaleEffect(zoom)
                        .offset(x:shifted ? horizontal*geometry.size.width : 0,
                                y:shifted ? vertical*geometry.size.height : 0)
                } else { Text(shifted ? "Исходник" : "Референс").foregroundStyle(.secondary) }
            }.clipped()
        }
    }

    private func choose(_ label: String, selection: Binding<String>) -> some View {
        Picker(label,selection:selection) {
            Text("Выбрать").tag("")
            ForEach(photos) { Text($0.title).tag($0.preview) }
        }
    }

    private func persist() {
        guard let a=pair.0, let b=pair.1 else { return }
        let id=saved.isEmpty ? UUID().uuidString : saved
        let row:[String:Any]=["id":id,"title":a.title+" / "+b.title,"source":left,"target":right,"notes":note,
                              "settings":["zoom":zoom,"x":horizontal*100,"y":vertical*100,"wipe":wipe*100,"overlay":overlay]]
        store.withError {
            records=try await store.changeDocument("comparisons") {
                $0.removeAll { $0["id"] as? String == id }
                $0.insert(row,at:0)
            }
            saved=id
        }
    }

    private func restore() {
        guard let row=records.first(where:{$0["id"] as? String == saved}) else { return }
        let settings=row["settings"] as? [String:Any] ?? [:]
        left=row["source"] as? String ?? ""; right=row["target"] as? String ?? ""; note=row["notes"] as? String ?? ""
        zoom=settings["zoom"] as? Double ?? 1
        horizontal=(settings["x"] as? Double ?? 0)/100
        vertical=(settings["y"] as? Double ?? 0)/100
        wipe=(settings["wipe"] as? Double ?? 50)/100
        overlay=settings["overlay"] as? Bool ?? false
    }
}

struct SearchPanel: View {
    @ObservedObject var store: DesktopStore
    let initial: String?
    let open: (NativeReference) -> Void
    @State private var query = ""
    @State private var example = ""
    @State private var lightOnly = false
    @State private var searching = false
    @State private var result: [NativeReference] = []
    @State private var explanation = ""

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                TextField("Например: жёсткий боковой свет и холодные тени",text:$query).onSubmit(search)
                Picker("Фото-пример",selection:$example) {
                    Text("Без примера").tag("")
                    ForEach(store.photos.filter { $0.localURL != nil }) { Text($0.title).tag($0.preview) }
                }
                Toggle("Только свет",isOn:$lightOnly).disabled(example.isEmpty)
                Button("Найти",action:search).buttonStyle(.borderedProminent).disabled(searching || (query.isEmpty && example.isEmpty))
            }
            if searching { ProgressView("Проверяем локальный архив…") }
            if !explanation.isEmpty { Text(explanation).foregroundStyle(.secondary) }
            ScrollView {
                LazyVGrid(columns:[GridItem(.adaptive(minimum:145,maximum:210))],spacing:10) {
                    ForEach(result) { ref in
                        VStack(alignment:.leading) {
                            Button { open(ref) } label: { NativeMedia(reference:ref).aspectRatio(1,contentMode:.fit) }
                                .buttonStyle(.plain)
                            Text(ref.title).lineLimit(1).font(.caption)
                            Button("На доску") { store.place([ref]) }
                        }
                    }
                }
            }
        }.padding(16).task {
            if let initial,let ref=store.items.first(where:{$0.id==initial}) {
                example=ref.preview
                search()
            }
        }
    }

    private func search() {
        guard !searching,!query.isEmpty || !example.isEmpty else { return }
        searching=true
        store.withError {
            defer { searching=false }
            let response=try await store.call(["op":"search","body":["query":query,"example":example,"lightOnly":lightOnly]]) as? [String:Any]
            result=(response?["items"] as? [[String:Any]] ?? []).map(NativeReference.init)
            let signals=response?["signals"] as? [String] ?? []
            explanation=result.isEmpty ? "Ничего не найдено" : (["Найдено: \(result.count)"]+signals).joined(separator:" · ")
        }
    }
}

struct ReviewPanel: View {
    @ObservedObject var store: DesktopStore
    @State private var frames: [NativeReference] = []
    @State private var picker = ""
    @State private var brief = ""
    @State private var key = ""
    @State private var model = ""
    @State private var summary = ""
    @State private var observations: [[String:Any]] = []
    @State private var evidence: [[String:Any]] = []
    @State private var notes: [[String:Any]] = []
    @State private var feedback = ""
    @State private var working = false

    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:12) {
                HStack {
                    Picker("Кадр",selection:$picker) {
                        Text("Выбрать").tag("")
                        ForEach(store.photos.filter { $0.localURL != nil }) { Text($0.title).tag($0.id) }
                    }
                    Button("Добавить") { add(store.items.filter{$0.id==picker}) }
                    Button("Из выделения") { add(store.selected) }
                }
                ForEach(Array(frames.enumerated()),id:\.element.id) { index,ref in
                    HStack {
                        NativeMedia(reference:ref).frame(width:50,height:38)
                        Text("\(index+1). \(ref.title)")
                        Spacer()
                        Button("Убрать") { frames.removeAll { $0.id==ref.id } }
                    }
                }
                TextField("Бриф",text:$brief,axis:.vertical).lineLimit(2...4)
                HStack {
                    SecureField("Gemini API key",text:$key)
                    TextField("Модель по умолчанию",text:$model)
                    Button("Отправить кадры в Gemini",action:review).buttonStyle(.borderedProminent)
                        .disabled(working || frames.isEmpty)
                }
                if working { ProgressView("Gemini разбирает кадры…") }
                if !summary.isEmpty || !observations.isEmpty {
                    TextField("Заметка",text:$summary,axis:.vertical).lineLimit(3...8)
                    observationsList(observations,evidence)
                    Button("Сохранить к доске",action:save).disabled(summary.isEmpty)
                }
                if !feedback.isEmpty { Text(feedback).foregroundStyle(.secondary) }
                ForEach(notes.indices,id:\.self) { index in
                    let row=notes[index]
                    DisclosureGroup(row["brief"] as? String ?? row["model"] as? String ?? "Разбор") {
                        Text(row["note"] as? String ?? "")
                        observationsList(row["observations"] as? [[String:Any]] ?? [],row["frames"] as? [[String:Any]] ?? [])
                    }.padding(.vertical,4)
                }
            }.padding(16)
        }.task {
            add(store.selected)
            store.withError { notes=try await store.document("reviews") }
        }
    }

    private func observationsList(_ rows: [[String:Any]],_ refs: [[String:Any]]) -> some View {
        VStack(alignment:.leading,spacing:5) {
            ForEach(rows.indices,id:\.self) { i in
                let row=rows[i]
                Text(row["text"] as? String ?? "")
                HStack {
                    ForEach(row["frames"] as? [Int] ?? [],id:\.self) { n in
                        if n>0 && refs.indices.contains(n-1),let token=refs[n-1]["preview"] as? String {
                            Button("Кадр \(n)") {
                                if let url=store.items.first(where:{$0.preview==token})?.localURL {
                                    NSWorkspace.shared.activateFileViewerSelecting([url])
                                }
                            }.buttonStyle(.link)
                        }
                    }
                }
            }
        }
    }

    private func add(_ refs: [NativeReference]) {
        for ref in refs where frames.count<8 && ref.localURL != nil && ref.kind=="Фото" && !frames.contains(ref) { frames.append(ref) }
    }

    private func review() {
        let submission=frames.map(\.record)
        working=true
        feedback=""
        store.withError {
            defer { working=false }
            let response=try await store.api("/api/workflow/review","POST",body:["key":key,"model":model,"brief":brief,"refs":submission]) as? [String:Any]
            summary=response?["summary"] as? String ?? ""
            observations=response?["observations"] as? [[String:Any]] ?? []
            evidence=submission
        }
    }

    private func save() {
        let row:[String:Any]=["id":UUID().uuidString,"brief":brief,"model":model,"note":summary,"frames":evidence,
                              "observations":observations,"created":ISO8601DateFormatter().string(from:Date())]
        store.withError {
            notes=try await store.changeDocument("reviews") { $0.insert(row,at:0) }
            feedback="Заметка сохранена к доске."
        }
    }
}
