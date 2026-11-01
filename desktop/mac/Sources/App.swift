import AppKit
import SwiftUI

@main
struct NeurogenesisApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var app = AppState()

    var body: some Scene {
        WindowGroup("Neurogenesis") {
            ContentView()
                .environmentObject(app)
                .frame(minWidth: 1100, minHeight: 680)
                .onAppear { delegate.app = app }
        }
        .defaultSize(width: 1500, height: 920)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Project") { app.newProject() }.keyboardShortcut("n")
                Button("Open…") { app.openProject() }.keyboardShortcut("o")
                Divider()
                Button("Save Project") { app.saveProject() }.keyboardShortcut("s")
                Button("Save Project As…") { app.saveProject(as: true) }.keyboardShortcut("s", modifiers: [.command, .shift])
                Button("Export Network JSON…") { app.saveNetwork() }.keyboardShortcut("e")
            }
            CommandGroup(replacing: .undoRedo) {
                Button("Undo") { app.undo() }.keyboardShortcut("z")
                Button("Redo") { app.redo() }.keyboardShortcut("z", modifiers: [.command, .shift])
            }
            CommandMenu("Network") {
                Button("Grow Body Plan") { app.grow() }.keyboardShortcut("g")
                Button("Develop Step by Step") { app.growSteps() }.keyboardShortcut("g", modifiers: [.command, .shift])
                Divider()
                ForEach(Array(Tool.allCases.enumerated()), id: \.offset) { k, t in
                    Button(t.rawValue) { app.tool = t }.keyboardShortcut(KeyEquivalent(Character("\(k + 1)")))
                }
                Divider()
                Button("Select All Neurons") { app.selectAll() }.keyboardShortcut("a", modifiers: [.command, .option])
                Button("Delete Selection") { app.deleteSelection() }.keyboardShortcut(.delete, modifiers: [.command])
            }
            CommandMenu("Simulation") {
                Button(app.running ? "Pause" : "Run") { app.running.toggle() }.keyboardShortcut("r")
                Button("Step 1 ms") { app.engine.step(1) }.keyboardShortcut(.rightArrow, modifiers: [.command])
                Button("Step 100 ms") { app.engine.step(100) }.keyboardShortcut(.rightArrow, modifiers: [.command, .shift])
                Button("Reset") { app.resetSimulation() }.keyboardShortcut("k")
                Divider()
                Toggle("Drive Inputs", isOn: Binding(get: { app.driveInputs }, set: { app.driveInputs = $0 })).keyboardShortcut("i")
            }
            CommandGroup(after: .sidebar) {
                Button("Frame All") { app.frameAll() }.keyboardShortcut("f", modifiers: [.command, .shift])
                Toggle("Raster", isOn: Binding(get: { app.showRaster }, set: { app.showRaster = $0 }))
                Toggle("Inspector", isOn: Binding(get: { app.showInspector }, set: { app.showInspector = $0 })).keyboardShortcut("i", modifiers: [.command, .option])
                Divider()
                ForEach(Section.allCases) { s in Button(s.rawValue) { app.section = s } }
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var app: AppState?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { MainActor.assumeIsolated { app?.bridge.stop() } }
    func application(_ application: NSApplication, open urls: [URL]) {
        MainActor.assumeIsolated { for u in urls { app?.openFile(u) } }
    }
}
