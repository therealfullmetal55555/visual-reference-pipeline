import AppKit
import CoreImage
import ImageIO
import SwiftUI

struct PhotoEditor: View {
    @ObservedObject var store: DesktopStore
    @State private var choice = ""
    @State private var brightness = 0.0
    @State private var contrast = 1.0
    @State private var saturation = 1.0
    @State private var warmth = 6500.0
    @State private var quarterTurns = 0
    @State private var original = false
    @State private var rendered: NSImage?
    private let context = CIContext()
    private var photos: [NativeReference] { store.photos.filter { $0.localURL != nil } }
    private var selected: NativeReference? { photos.first { $0.id == choice } }
    private var inputs: [Double] { [brightness,contrast,saturation,warmth,Double(quarterTurns)] }

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Picker("Изображение",selection:$choice) {
                    Text("Выбрать").tag("")
                    ForEach(photos) { Text($0.title).tag($0.id) }
                }
                Button("Импортировать…",action:store.importFiles)
                Toggle("Оригинал",isOn:$original).toggleStyle(.button)
                Button("Повернуть ↻") { quarterTurns=(quarterTurns+1)%4 }
            }
            Group {
                if original,let selected { NativeMedia(reference:selected,fit:true) }
                else if let rendered { Image(nsImage:rendered).resizable().scaledToFit() }
                else { Text("Выберите изображение из архива.").foregroundStyle(.secondary) }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
            HStack {
                Slider(value:$brightness,in:-0.55...0.55) { Text("Яркость") }
                Slider(value:$contrast,in:0.35...2) { Text("Контраст") }
                Slider(value:$saturation,in:0...2) { Text("Цвет") }
                Slider(value:$warmth,in:3500...9500) { Text("Температура") }
            }.disabled(selected == nil)
            HStack {
                Button("Сбросить") { brightness=0;contrast=1;saturation=1;warmth=6500;quarterTurns=0 }
                Spacer()
                Button("Скачать PNG") {
                    store.withError {
                        guard let image=render(maxSize:0) else { throw DesktopError("Не удалось открыть изображение.") }
                        try nativeSave(imagePNG(image),named:"edited-reference.png")
                    }
                }.buttonStyle(.borderedProminent).disabled(selected == nil)
            }
        }.padding(16).task { choice=store.selected.first(where:{$0.kind=="Фото" && $0.localURL != nil})?.id ?? "" }
            .onChange(of:choice) { _ in rendered=render(maxSize:1050) }
            .onChange(of:inputs) { _ in rendered=render(maxSize:1050) }
    }

    private func render(maxSize: Int) -> NSImage? {
        guard let url=selected?.localURL, var image=CIImage(contentsOf:url,options:[.applyOrientationProperty:true]) else { return nil }
        if maxSize>0 {
            let scale=min(1,CGFloat(maxSize)/max(image.extent.width,image.extent.height))
            image=image.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
        }
        image=image.applyingFilter("CIColorControls",parameters:[
            kCIInputBrightnessKey:brightness,kCIInputContrastKey:contrast,kCIInputSaturationKey:saturation,
        ]).applyingFilter("CITemperatureAndTint",parameters:[
            "inputNeutral":CIVector(x:6500,y:0),"inputTargetNeutral":CIVector(x:warmth,y:0),
        ])
        image=image.oriented(forExifOrientation:[1,6,3,8][quarterTurns])
        guard let result=context.createCGImage(image,from:image.extent) else { return nil }
        return NSImage(cgImage:result,size:NSSize(width:result.width,height:result.height))
    }
}

struct CollagePanel: View {
    @ObservedObject var store: DesktopStore
    @State private var columns=3
    @State private var choice=""
    @State private var frames: [NativeReference]=[]

    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Picker("Кадр",selection:$choice) {
                    Text("Выбрать").tag("")
                    ForEach(store.photos.filter { $0.localURL != nil }) { Text($0.title).tag($0.id) }
                }
                Button("Добавить") { add(store.photos.filter { $0.id == choice }) }.disabled(choice.isEmpty)
                Button("Из выделения") { add(store.selected) }.disabled(store.selection.isEmpty)
                Stepper("Колонки: \(columns)",value:$columns,in:1...6)
                Button("Скачать PNG") {
                    store.withError {
                        let renderer=ImageRenderer(content:grid.frame(width:1200))
                        guard let sheet=renderer.nsImage else { throw DesktopError("Не удалось собрать коллаж.") }
                        try nativeSave(imagePNG(sheet),named:"contact-sheet.png")
                    }
                }.disabled(frames.isEmpty)
            }
            if frames.isEmpty { Text("Добавьте локальные фотографии.").foregroundStyle(.secondary) }
            ScrollView { grid }
        }.padding(16).task { add(store.selected) }
    }

    private var grid: some View {
        LazyVGrid(columns:Array(repeating:GridItem(.flexible(),spacing:6),count:columns),spacing:6) {
            ForEach(frames) { frame in
                NativeMedia(reference:frame).aspectRatio(1,contentMode:.fit)
                    .contextMenu { Button("Убрать") { frames.removeAll { $0.id == frame.id } } }
            }
        }.padding(6).background(Color(nsColor:.windowBackgroundColor))
    }

    private func add(_ references: [NativeReference]) {
        for frame in references where frame.localURL != nil && frame.kind=="Фото" && !frames.contains(frame) && frames.count<30 {
            frames.append(frame)
        }
    }
}
