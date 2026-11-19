import SwiftUI

struct WorkspacePalette {
    let dark: Bool
    var canvas: Color { shade(8,238) }
    var sidebar: Color { shade(16,229) }
    var surface: Color { shade(23,221) }
    var selected: Color { shade(41,196) }
    var line: Color { shade(37,199) }
    var text: Color { shade(240,17) }
    var muted: Color { shade(146,85) }
    private func shade(_ darkValue: Double, _ lightValue: Double) -> Color {
        Color(white:(dark ? darkValue : lightValue)/255)
    }
}

struct MonoButton: ButtonStyle {
    let palette: WorkspacePalette
    var active = false
    var outlined = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(active || configuration.isPressed ? palette.text : palette.muted)
            .background(configuration.isPressed || active ? palette.selected : .clear, in: RoundedRectangle(cornerRadius:6))
            .overlay {
                if outlined { RoundedRectangle(cornerRadius:6).strokeBorder(palette.line) }
            }
            .contentShape(Rectangle())
    }
}

struct WorkspaceSidebar: View {
    let palette: WorkspacePalette
    @Binding var page: DesktopPage
    @Binding var collapsed: Bool

    var body: some View {
        VStack(alignment:.leading,spacing:7) {
            HStack {
                Image(nsImage:NSApp.applicationIconImage)
                    .resizable().interpolation(.high).frame(width:34,height:34)
                    .accessibilityHidden(true)
                if !collapsed {
                    Text("Visual Reference").font(.system(size:12,weight:.medium)).lineLimit(1)
                    Spacer(minLength:0)
                }
            }.frame(height:45).padding(.horizontal,collapsed ? 7 : 9).padding(.bottom,12)
            ScrollView {
                VStack(alignment:.leading,spacing:4) {
                    ForEach([DesktopPage.archive,.board,.collections]) { nav($0) }
                    Rectangle().fill(palette.line).frame(height:1).padding(.vertical,8)
                    ForEach([DesktopPage.editor,.timeline,.comparison,.collage,.shots,.search,.review]) { nav($0) }
                }
            }
            Spacer(minLength:4)
            Button { collapsed.toggle() } label: {
                HStack(spacing:12) {
                    Image(systemName:collapsed ? "sidebar.leading" : "sidebar.left").frame(width:18)
                    if !collapsed { Text("Свернуть"); Spacer(minLength:0) }
                }.frame(maxWidth:.infinity,alignment:collapsed ? .center : .leading).padding(.horizontal,10).frame(height:34)
            }.buttonStyle(MonoButton(palette:palette,outlined:false))
                .help(collapsed ? "Развернуть сайдбар" : "Свернуть сайдбар")
        }.font(.system(size:13))
            .padding(.horizontal,collapsed ? 9 : 14).padding(.vertical,13)
            .frame(width:collapsed ? 64 : 214)
            .frame(maxHeight:.infinity,alignment:.top)
            .background(palette.sidebar)
    }

    private func nav(_ item: DesktopPage) -> some View {
        Button { page=item } label: {
            HStack(spacing:12) {
                Image(systemName:item.symbol).font(.system(size:15)).frame(width:18)
                if !collapsed { Text(item.rawValue).lineLimit(1); Spacer(minLength:0) }
            }.frame(maxWidth:.infinity,alignment:collapsed ? .center : .leading).padding(.horizontal,10).frame(height:37)
        }.buttonStyle(MonoButton(palette:palette,active:page==item,outlined:false))
            .help(item.rawValue)
            .accessibilityLabel(item.rawValue)
    }
}

struct WorkspaceIcon: View {
    let name: String
    let label: String
    let palette: WorkspacePalette
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action:action) {
            Image(systemName:name).font(.system(size:15,weight:.regular)).frame(width:35,height:35)
        }.buttonStyle(MonoButton(palette:palette,active:active))
            .help(label).accessibilityLabel(label)
    }
}
