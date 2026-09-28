import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

// Locals — Containers / Localhosts / Ports. Panel chrome mirrors
// im0001gt.hw-tooltip (HardwareTooltip.qml): 380×560, display hero,
// Style.font.{display,title,caption,body,icon}, Style.space(14) rhythm,
// dim=Qt.darker(fg,1.4), hover/selected fills, thin accent meters/LEDs.
// Header toolbar glyphs (Nerd Font):  Containers · 󰒋 Localhosts · 󰌗 Ports ·
// 󰦠 Default · 󰒺 Sort · 󰒓 Options. Discovery stays in CLI.
// brittiiaa.widgets embeds by lifting KeyboardPanel content into a card.

Panel {
  id: root
  moduleName: "wszaq.locals"
  ipcTarget: "wszaq.locals"

  readonly property color hoverFill: bar
    ? Style.hoverFillFor(bar.foreground, Color.accent)
    : Style.hoverFill
  readonly property color selectedFill: bar
    ? Style.selectedFillFor(bar.foreground, Color.accent)
    : Style.selectedFill
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.4)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property int pollInterval: Math.max(2, Number(root.setting("pollIntervalSec", 5)) || 5)
  readonly property bool showContainers: root.boolSetting("showContainers", true)
  readonly property bool showLocalhosts: root.boolSetting("showLocalhosts", true)
  readonly property bool showPorts: root.boolSetting("showPorts", false)
  readonly property string sortMode: {
    var raw = String(root.setting("sortMode", "default") || "default").toLowerCase()
    if (raw === "a-z" || raw === "alpha" || raw === "name") return "az"
    if (raw === "az" || raw === "port" || raw === "default") return raw
    return "default"
  }

  // Density: mirror im0001gt.hw-tooltip / Power — 380-wide hero popup,
  // Style.space(14) section rhythm, content-sized with a scroll cap.
  readonly property int panelWidth: Style.space(380)
  readonly property int panelMaxHeight: Style.space(560)
  readonly property int sectionListMaxHeight: Style.space(200)
  readonly property int rowBtnHeight: Style.space(22)
  readonly property int headerBtnHeight: Style.space(28)

  readonly property string heroMeta: {
    var parts = [root.running + " of " + root.total + " running"]
    if (root.paused > 0) parts.push(root.paused + " paused")
    if (!root.dockerUp && root.showContainers) parts.push("Docker down")
    if (root.unknown > 0) parts.push(root.unknown + " unknown")
    return parts.join(" · ")
  }

  readonly property string pluginDir: Quickshell.env("HOME") + "/.config/omarchy/plugins/wszaq.locals"
  readonly property string cli: pluginDir + "/bin/wszaq-locals"

  property var status: ({
    schemaVersion: 1,
    docker: { reachable: false },
    counts: { total: 0, running: 0, paused: 0, unknown: 0 },
    filters: { showContainers: true, showLocalhosts: true, showPorts: false },
    sortMode: "default",
    configPath: "",
    configErrors: [],
    groups: { containers: [], localhosts: [], ports: [] },
    targets: [],
    probedAt: ""
  })
  property int statusSeq: 0
  property int appliedSeq: 0
  property string busyId: ""
  property string footerError: ""
  property string focusSection: "header"
  property int selectedIndex: 0
  property bool cursorActive: false
  property string panelPage: "main"  // "main" | "prefs"

  readonly property var groups: status && status.groups ? status.groups : ({ containers: [], localhosts: [], ports: [] })
  readonly property var allContainers: groups.containers || []
  readonly property var allLocalhosts: groups.localhosts || []
  readonly property var allPorts: groups.ports || []
  readonly property var containerTargets: showContainers ? allContainers : []
  readonly property var localhostTargets: showLocalhosts ? allLocalhosts : []
  readonly property var portTargets: showPorts ? allPorts : []

  readonly property int running: status && status.counts ? status.counts.running : 0
  readonly property int total: status && status.counts ? status.counts.total : 0
  readonly property int paused: status && status.counts ? status.counts.paused : 0
  readonly property int unknown: status && status.counts ? status.counts.unknown : 0
  readonly property bool dockerUp: status && status.docker && status.docker.reachable
  readonly property bool hasError: unknown > 0 || (status.configErrors && status.configErrors.length > 0) || footerError !== ""
  readonly property bool anyKindOn: showContainers || showLocalhosts || showPorts
  readonly property int visibleCount: containerTargets.length + localhostTargets.length + portTargets.length
  readonly property bool listEmpty: visibleCount === 0

  readonly property bool showContainersSection: showContainers && (
    containerTargets.length > 0 || (!dockerUp && !listEmpty) || (containerTargets.length === 0 && !listEmpty)
  )
  readonly property bool showLocalhostsSection: showLocalhosts && (
    localhostTargets.length > 0 || (localhostTargets.length === 0 && !listEmpty)
  )
  readonly property bool showPortsSection: showPorts && (
    portTargets.length > 0 || (portTargets.length === 0 && !listEmpty)
  )

  readonly property string sortModeLabel: {
    if (root.sortMode === "az") return "A–Z"
    if (root.sortMode === "port") return "Port"
    return "Default"
  }

  function boolSetting(name, fallback) {
    var value = root.setting(name, fallback)
    if (typeof value === "string") {
      var s = value.toLowerCase()
      if (s === "true" || s === "1" || s === "yes" || s === "on") return true
      if (s === "false" || s === "0" || s === "no" || s === "off") return false
    }
    if (value === undefined || value === null) return !!fallback
    return !!value
  }

  function persistSettings(patch) {
    var next = Object.assign({}, root.settings || {})
    for (var k in patch) next[k] = patch[k]
    root.settings = next
    if (root.bar && root.bar.shell)
      root.bar.shell.updateEntryInline(root.moduleName, root.settings)
  }

  function setKindVisible(key, value) {
    var patch = {}
    patch[key] = !!value
    root.persistSettings(patch)
    root.refresh()
  }

  function setPollIntervalSec(sec) {
    var n = Math.max(2, Math.min(60, Math.floor(Number(sec) || 5)))
    root.persistSettings({ pollIntervalSec: n })
  }

  function setSortMode(mode) {
    var m = String(mode || "default").toLowerCase()
    if (m === "a-z" || m === "alpha") m = "az"
    if (m !== "az" && m !== "port" && m !== "default") m = "default"
    root.persistSettings({ sortMode: m })
    root.refresh()
  }

  function cycleSortMode() {
    if (root.sortMode === "default") root.setSortMode("az")
    else if (root.sortMode === "az") root.setSortMode("port")
    else root.setSortMode("default")
  }

  function resetToDefault() {
    root.panelPage = "main"
    root.footerError = ""
    if (root.sortMode !== "default") root.setSortMode("default")
    else root.refresh()
  }

  // State LED / thin meter colors — theme tokens only (hardware Meter accent).
  function stateColor(state, hasError) {
    if (hasError || state === "unknown" || state === "error") return Color.urgent
    if (state === "running") return Color.accent
    if (state === "paused") return Util.alpha(root.foreground, 0.45)
    return Util.alpha(root.foreground, 0.18)  // stopped / other
  }

  function stateMeterPercent(state) {
    if (state === "running") return 100
    if (state === "paused") return 45
    if (state === "stopped") return 12
    return 28  // unknown
  }

  function barText() {
    var glyph = hasError ? "󰀦" : ""
    if (running <= 0)
      return glyph
    return glyph + " " + Math.min(running, 9)
  }

  function barTooltip() {
    var parts = [running + " of " + total + " running"]
    if (paused > 0) parts.push(paused + " paused")
    if (!dockerUp && showContainers) parts.push("Docker unavailable")
    if (unknown > 0) parts.push(unknown + " unknown")
    if (!showPorts) parts.push("Ports hidden")
    return "Locals — " + parts.join(" · ")
  }

  function applyStatus(raw, seq) {
    if (seq !== undefined && seq < root.appliedSeq) return
    var text = String(raw || "").trim()
    if (!text) return
    try {
      var parsed = JSON.parse(text)
      root.status = parsed
      if (seq !== undefined) root.appliedSeq = seq
      root.footerError = ""
      if (parsed.configErrors && parsed.configErrors.length)
        root.footerError = String(parsed.configErrors[0])
    } catch (e) {
      console.warn("wszaq.locals", "status JSON parse failed")
      root.footerError = "bad status JSON"
    }
  }

  function refresh() {
    if (statusProc.running) return
    root.statusSeq += 1
    statusProc.seq = root.statusSeq
    statusProc.command = [
      root.cli, "status", "--json",
      "--show-containers", root.showContainers ? "1" : "0",
      "--show-localhosts", root.showLocalhosts ? "1" : "0",
      "--show-ports", root.showPorts ? "1" : "0",
      "--sort-mode", root.sortMode
    ]
    statusProc.running = true
  }

  function runAction(id, action) {
    if (!id || !action || root.busyId !== "") return
    root.busyId = id
    actionProc.command = [root.cli, action, id]
    actionProc.running = true
  }

  function ignoreTarget(id) {
    if (!id || root.busyId !== "") return
    root.busyId = id
    actionProc.command = [root.cli, "ignore", id]
    actionProc.running = true
  }

  function setAutostart(id, enabled) {
    if (!id || root.busyId !== "") return
    root.busyId = id
    actionProc.command = [root.cli, enabled ? "autostart-on" : "autostart-off", id]
    actionProc.running = true
  }

  function runAutostartNow() {
    if (root.busyId !== "") return
    root.busyId = "__autostart__"
    actionProc.command = [root.cli, "autostart"]
    actionProc.running = true
  }

  function openUrl(url) {
    if (!url) return
    Util.execArgv(["xdg-open", String(url)])
  }

  function launchDockerTui() {
    Util.execArgv(["omarchy-launch-docker-tui"])
  }

  function openConfig() {
    var path = status && status.configPath ? String(status.configPath) : ""
    if (!path)
      path = Quickshell.env("HOME") + "/.config/omarchy/locals/targets.json"
    Util.execArgv(["omarchy-launch-editor", path])
  }

  function openConfigDir() {
    Util.execArgv(["xdg-open", Quickshell.env("HOME") + "/.config/omarchy/locals"])
  }

  function actionLabel(action) {
    if (action === "start") return "Start"
    if (action === "stop") return "Stop"
    if (action === "pause") return "Pause"
    if (action === "resume") return "Resume"
    if (action === "restart") return "Restart"
    return action || ""
  }

  function stateLabel(state) {
    if (state === "running") return "RUN"
    if (state === "paused") return "PAUSE"
    if (state === "stopped") return "STOP"
    return "??"
  }

  function emptyHint() {
    if (!root.anyKindOn)
      return "All kinds off — toggle Containers, Localhosts, or Ports"
    if (!root.dockerUp && root.showContainers && !root.showLocalhosts && !root.showPorts)
      return "No containers — Docker unavailable"
    if (!root.dockerUp && root.showContainers)
      return "No matching services (Docker unavailable)"
    return "Nothing matching the active filters"
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: {
    if (!opened) root.panelPage = "main"
  }

  Process {
    id: statusProc
    property int seq: 0
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyStatus(text, statusProc.seq)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var err = String(text || "").trim()
        if (err) console.warn("wszaq.locals", err.slice(0, 400))
      }
    }
  }

  Process {
    id: actionProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var text = String(text || "").trim()
        try {
          var parsed = JSON.parse(text)
          if (parsed && parsed.ok === false)
            root.footerError = String(parsed.error || "action failed")
        } catch (e) {}
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var err = String(text || "").trim()
        if (err) console.warn("wszaq.locals", err.slice(0, 400))
      }
    }
    onExited: function(code) {
      root.busyId = ""
      root.refresh()
    }
  }

  Timer {
    interval: root.pollInterval * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (root.busyId !== "") return
      if (!statusProc.running) root.refresh()
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.barText()
    foreground: root.hasError ? Color.urgent : Color.bar.text
    tooltipText: root.barTooltip()
    opacity: root.running === 0 && root.total > 0 ? 0.55 : 1.0
    onPressed: function(b) {
      if (b === Qt.RightButton) root.launchDockerTui()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(root.panelWidth)
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, root.panelMaxHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      ScrollView {
        id: scrollArea
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: panelColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

        Column {
          id: panelColumn
          width: scrollArea.availableWidth
          spacing: Style.space(14)

          // ── Main page ───────────────────────────────────────────────
          Column {
            width: parent.width
            spacing: Style.space(14)
            visible: root.panelPage === "main"

            // Hero — matches im0001gt.hw-tooltip / Power
            Item {
              width: parent.width
              implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroValue.implicitHeight)

              Text {
                id: heroIcon
                text: root.hasError ? "󰀦" : ""
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Column {
                id: heroLabels
                anchors.left: heroIcon.right
                anchors.leftMargin: Style.space(14)
                anchors.right: heroValue.left
                anchors.rightMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(2)

                Text {
                  textFormat: Text.PlainText
                  text: "Locals"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                  elide: Text.ElideRight
                  width: parent.width
                }

                Text {
                  textFormat: Text.PlainText
                  text: root.heroMeta.toUpperCase()
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                  font.letterSpacing: Style.font.caption * 0.12
                  elide: Text.ElideRight
                  width: parent.width
                }
              }

              Column {
                id: heroValue
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(4)
                width: Style.space(48)

                Text {
                  textFormat: Text.PlainText
                  text: root.running + "/" + root.total
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                  horizontalAlignment: Text.AlignRight
                  width: parent.width
                }

                // Aggregate running meter — hardware SectionBlock Meter scale.
                StateMeter {
                  width: parent.width
                  implicitHeight: Style.space(4)
                  percent: root.total > 0
                    ? Math.round(100 * root.running / root.total)
                    : 0
                  fillColor: root.hasError ? Color.urgent : Color.accent
                }
              }
            }

            // Compact icon toolbar (replaces wordy KindChip strip).
            // Glyphs:  Containers · 󰒋 Localhosts · 󰌗 Ports · 󰦠 Default · 󰒺 Sort · 󰒓 Options
            Row {
              width: parent.width
              spacing: Style.space(6)

              ToolbarIcon {
                iconText: ""
                tooltipText: "Containers"
                checked: root.showContainers
                toggleMode: true
                onActivated: root.setKindVisible("showContainers", !root.showContainers)
              }
              ToolbarIcon {
                iconText: "󰒋"
                tooltipText: "Localhosts"
                checked: root.showLocalhosts
                toggleMode: true
                onActivated: root.setKindVisible("showLocalhosts", !root.showLocalhosts)
              }
              ToolbarIcon {
                iconText: "󰌗"
                tooltipText: "Ports"
                checked: root.showPorts
                toggleMode: true
                onActivated: root.setKindVisible("showPorts", !root.showPorts)
              }
              ToolbarIcon {
                iconText: "󰦠"
                tooltipText: "Default sort"
                checked: false
                toggleMode: false
                onActivated: root.resetToDefault()
              }
              ToolbarIcon {
                iconText: "󰒺"
                tooltipText: "Sort: " + root.sortModeLabel + " (Default → A–Z → Port)"
                checked: root.sortMode !== "default"
                toggleMode: false
                onActivated: root.cycleSortMode()
              }
              ToolbarIcon {
                iconText: "󰒓"
                tooltipText: "Options"
                checked: root.panelPage === "prefs"
                toggleMode: false
                onActivated: root.panelPage = "prefs"
              }
            }

            Column {
              width: parent.width
              spacing: Style.space(6)
              visible: root.listEmpty

              Text {
                width: parent.width
                text: root.emptyHint()
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              Text {
                width: parent.width
                visible: root.anyKindOn
                text: root.showPorts
                  ? "Optional: pin labels/URLs or Ignore noisy rows"
                  : "Ports stay off by default — toggle the Ports icon to debug listeners"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }
            }

            LocalsSection {
              visible: root.showContainersSection || (root.showContainers && !root.dockerUp && root.listEmpty)
              icon: ""
              title: "CONTAINERS"
              value: root.containerTargets.length > 0 ? String(root.containerTargets.length) : ""
              emptyText: !root.dockerUp ? "Docker unavailable" : (root.containerTargets.length === 0 ? "No containers" : "")
              model: root.containerTargets
            }

            LocalsSection {
              visible: root.showLocalhostsSection
              icon: "󰒋"
              title: "LOCALHOSTS"
              value: root.localhostTargets.length > 0 ? String(root.localhostTargets.length) : ""
              emptyText: root.localhostTargets.length === 0 ? "No local app servers" : ""
              model: root.localhostTargets
            }

            LocalsSection {
              visible: root.showPortsSection
              icon: "󰌗"
              title: "PORTS"
              value: root.portTargets.length > 0 ? String(root.portTargets.length) : ""
              emptyText: root.portTargets.length === 0 ? "No other listeners" : ""
              model: root.portTargets
            }

            Column {
              width: parent.width
              spacing: Style.space(6)
              visible: !root.listEmpty || root.footerError !== ""

              PanelSeparator { foreground: root.foreground }

              Text {
                width: parent.width
                visible: root.footerError !== ""
                text: root.footerError
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
                opacity: 0.85
              }

              Row {
                width: parent.width
                spacing: Style.space(8)

                Text {
                  text: root.status.probedAt ? ("probed " + root.status.probedAt) : ""
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                  width: parent.width - dockerTuiBtn.width - Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                }

                Button {
                  id: dockerTuiBtn
                  text: "Docker TUI"
                  fontSize: Style.font.caption
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  bordered: true
                  onClicked: root.launchDockerTui()
                }
              }
            }
          }

          // ── Preferences page ────────────────────────────────────────
          Column {
            width: parent.width
            spacing: Style.space(14)
            visible: root.panelPage === "prefs"

            Row {
              width: parent.width
              spacing: Style.space(14)

              PanelActionButton {
                iconText: "󰁍"
                tooltipText: "Back"
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.panelPage = "main"
              }

              Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Preferences"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
              }
            }

            Text {
              width: parent.width
              text: "Localhosts = pinned / HTTP-ish / common app ports & process names. Ports = everything else (off by default). User apps with a PID get Stop/Pause/Resume/Restart from the row Actions menu."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            PanelSectionHeader {
              text: "KINDS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Toggle {
              width: parent.width
              label: "Containers"
              description: "Docker containers (controllable)"
              checked: root.showContainers
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setKindVisible("showContainers", !root.showContainers)
            }

            Toggle {
              width: parent.width
              label: "Localhosts"
              description: "Local app servers you usually care about"
              checked: root.showLocalhosts
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setKindVisible("showLocalhosts", !root.showLocalhosts)
            }

            Toggle {
              width: parent.width
              label: "Ports"
              description: "Other listeners — noisy; off by default"
              checked: root.showPorts
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setKindVisible("showPorts", !root.showPorts)
            }

            PanelSeparator { foreground: root.foreground }

            PanelSectionHeader {
              text: "SORT"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              width: parent.width
              text: "Default = state then name/port. A–Z = label. Port = port number."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Row {
              spacing: Style.space(6)
              KindChip {
                label: "Default"
                checked: root.sortMode === "default"
                onToggled: root.setSortMode("default")
              }
              KindChip {
                label: "A–Z"
                checked: root.sortMode === "az"
                onToggled: root.setSortMode("az")
              }
              KindChip {
                label: "Port"
                checked: root.sortMode === "port"
                onToggled: root.setSortMode("port")
              }
            }

            PanelSeparator { foreground: root.foreground }

            NumberField {
              width: parent.width
              label: "Poll interval (seconds)"
              value: root.pollInterval
              from: 2
              to: 60
              stepSize: 1
              foreground: root.foreground
              fontFamily: root.fontFamily
              onModified: function(v) { root.setPollIntervalSec(v) }
            }

            PanelSeparator { foreground: root.foreground }

            PanelSectionHeader {
              text: "IGNORE & PINS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              width: parent.width
              text: "Row Ignore hides a discovered item (targets.json). Pins/ignore live at ~/.config/omarchy/locals/targets.json. System daemons and docker-proxy are never signaled."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              text: "Start on login marks live in ~/.config/omarchy/locals/autostart.json. Host apps need a captured recipe (saved while running). Enable the user unit once — see README."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            PrefsAction {
              label: "Run autostart now"
              onActivated: root.runAutostartNow()
            }
            PrefsAction {
              label: "Open targets.json"
              onActivated: root.openConfig()
            }
            PrefsAction {
              label: "Open config folder"
              onActivated: root.openConfigDir()
            }
            PrefsAction {
              label: "Open Docker TUI"
              onActivated: root.launchDockerTui()
            }
          }
        }
      }
    }
  }

  // Hardware-sized icon button (PanelActionButton: Style.space(22) / Style.font.icon).
  component ToolbarIcon: BorderSurface {
    id: tip
    property string iconText: ""
    property string tooltipText: ""
    property bool checked: false
    property bool toggleMode: false
    signal activated()

    readonly property real glyphSize: Style.font.icon
    readonly property real size: Math.max(Style.space(22), glyphSize + Style.spacing.sm * 2)
    readonly property bool hot: mouse.containsMouse

    implicitWidth: size
    implicitHeight: size
    radius: Style.cornerRadius
    // Active kind toggles: selectedFill; inactive: dim. Actions stay full opacity.
    opacity: tip.toggleMode ? (tip.checked ? 1.0 : 0.42) : 1.0
    Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }

    color: tip.checked
      ? Style.selectedFillFor(root.foreground, Color.accent)
      : (tip.hot ? Style.hoverFillFor(root.foreground, Color.accent) : "transparent")
    Behavior on color { ColorAnimation { duration: 60 } }

    borderSpec: tip.checked
      ? Border.controlSpec("selected", root.foreground, Color.accent)
      : (tip.hot
        ? Border.controlSpec("hover-cursor", root.foreground, Color.accent)
        : Border.controlSpec("normal", root.foreground, Color.accent))

    Text {
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: tip.iconText
      color: tip.toggleMode && !tip.checked ? root.dim : root.foreground
      font.family: root.fontFamily
      font.pixelSize: tip.glyphSize
    }

    MouseArea {
      id: mouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: tip.activated()
    }

    PanelToolTip {
      visible: tip.tooltipText !== "" && mouse.containsMouse
      text: tip.tooltipText
      fontFamily: root.fontFamily
    }
  }

  // Thin hardware Meter (accent track, animated width).
  component StateMeter: Item {
    property int percent: 0
    property color fillColor: Color.accent

    Rectangle {
      anchors.fill: parent
      radius: height / 2
      color: Util.alpha(root.foreground, 0.12)
    }
    Rectangle {
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      height: parent.height
      radius: height / 2
      color: Util.alpha(fillColor, 0.9)
      width: Math.max(parent.height, parent.width * Math.max(0, Math.min(100, percent)) / 100)
      Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
      Behavior on color { ColorAnimation { duration: 180 } }
    }
  }

  // One tight KPI cell under the accent meter (CPU / MEM / PIDs).
  component ResourceKpi: Item {
    property string label: ""
    property string value: "—"

    implicitHeight: kpiText.implicitHeight

    Text {
      id: kpiText
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: label + " " + value
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
      horizontalAlignment: Text.AlignLeft
    }
  }

  component StateLed: Rectangle {
    property string ledState: "stopped"
    property bool hasError: false
    width: Style.space(6)
    height: Style.space(6)
    radius: width / 2
    color: root.stateColor(ledState, hasError)
    Behavior on color { ColorAnimation { duration: 180 } }
  }

  // Section block mirroring hw-tooltip SectionBlock (icon + title + value).
  component LocalsSection: Column {
    id: section
    property string icon: ""
    property string title: ""
    property string value: ""
    property string emptyText: ""
    property var model: []

    width: parent ? parent.width : 0
    spacing: Style.space(6)

    PanelSeparator { foreground: root.foreground }

    Item {
      width: parent.width
      implicitHeight: Math.max(secIcon.implicitHeight, secTitle.implicitHeight, secValue.implicitHeight)

      Text {
        id: secIcon
        visible: section.icon !== ""
        text: section.icon
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        id: secTitle
        textFormat: Text.PlainText
        text: section.title
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        font.bold: true
        elide: Text.ElideRight
        anchors.left: secIcon.right
        anchors.leftMargin: Style.space(8)
        anchors.right: secValue.visible ? secValue.left : parent.right
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        id: secValue
        textFormat: Text.PlainText
        visible: section.value !== ""
        text: section.value
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        font.bold: true
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    Text {
      width: parent.width
      visible: section.emptyText !== "" && section.model.length === 0
      text: section.emptyText
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.WordWrap
    }

    SectionList {
      model: section.model
      visible: section.model.length > 0
    }
  }

  component SectionList: Flickable {
    id: sectionFlick
    property var model: []
    width: parent ? parent.width : 0
    height: Math.min(sectionCol.implicitHeight, root.sectionListMaxHeight)
    contentHeight: sectionCol.implicitHeight
    contentWidth: width
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    interactive: contentHeight > height

    Column {
      id: sectionCol
      width: sectionFlick.width
      spacing: Style.space(6)

      Repeater {
        model: sectionFlick.model
        TargetRow {
          required property var modelData
          width: sectionCol.width
          target: modelData
        }
      }
    }
  }

  component KindChip: Button {
    id: chip
    property string label: ""
    property bool checked: false
    signal toggled()

    text: (chip.checked ? "● " : "○ ") + chip.label
    fontSize: Style.font.bodySmall
    foreground: root.foreground
    fontFamily: root.fontFamily
    bordered: true
    selected: chip.checked
    opacity: checked ? 1.0 : 0.78
    onClicked: chip.toggled()
  }

  component PrefsAction: CursorSurface {
    property string label: ""
    signal activated()
    width: parent ? parent.width : 0
    implicitHeight: Style.space(30)
    foreground: root.foreground
    fill: root.hoverFill
    currentFill: root.selectedFill
    hasCursor: false
    Text {
      anchors.left: parent.left
      anchors.leftMargin: Style.space(6)
      anchors.verticalCenter: parent.verticalCenter
      text: label
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: activated()
    }
  }

  // One obvious Actions control → menu of legal lifecycle + Open/Ignore.
  component TargetRow: Item {
    id: row
    required property var target
    property bool busy: root.busyId === String(target.id || "")
    property bool menuOpen: false

    readonly property var actions: target.actions || []
    readonly property bool isDocker: target.kind === "docker"
    readonly property bool canIgnore: !!(target.discovered)
    readonly property bool hasUrl: !!(target.url)

    readonly property var menuEntries: {
      var order = ["start", "resume", "pause", "stop", "restart"]
      var out = []
      for (var i = 0; i < order.length; i++) {
        if (row.actions.indexOf(order[i]) >= 0)
          out.push({ kind: "action", id: order[i], label: root.actionLabel(order[i]) })
      }
      if (row.hasUrl)
        out.push({ kind: "open", id: "open", label: "Open" })
      if (!!target.canAutostart) {
        out.push({
          kind: "autostart",
          id: !!target.autostart ? "off" : "on",
          label: !!target.autostart ? "Start on login ✓" : "Start on login"
        })
      }
      if (row.isDocker)
        out.push({ kind: "docker-tui", id: "docker-tui", label: "Docker TUI" })
      if (row.canIgnore)
        out.push({ kind: "ignore", id: "ignore", label: "Ignore" })
      return out
    }

    readonly property string metaText: {
      if (target.kind === "port") {
        var comm = target.meta && target.meta.comm ? String(target.meta.comm) : ""
        return comm
      }
      return target.meta && target.meta.container ? String(target.meta.container) : ""
    }

    readonly property string titleText: {
      var base = String(target.label || target.id || "")
      if (row.metaText && target.kind === "port")
        return base + " · " + row.metaText
      return base
    }

    // KPI strip under the accent meter — Containers + Localhosts only.
    // Prefer flat kpi* fields (QObject.resources can collide with JSON key).
    readonly property bool showResources: {
      var g = String(target.group || "")
      if (g !== "container" && g !== "localhost")
        return false
      if (target.hasResourceKpis)
        return true
      var r = target.resources
      return !!(r && r.cpu !== undefined)
    }
    readonly property string kpiCpu: {
      if (target.kpiCpu !== undefined && target.kpiCpu !== null && String(target.kpiCpu) !== "")
        return String(target.kpiCpu)
      var r = target.resources
      return (r && r.cpu !== undefined) ? String(r.cpu) : "—"
    }
    readonly property string kpiMem: {
      if (target.kpiMem !== undefined && target.kpiMem !== null && String(target.kpiMem) !== "")
        return String(target.kpiMem)
      var r = target.resources
      return (r && r.mem !== undefined) ? String(r.mem) : "—"
    }
    readonly property string kpiThird: {
      if (target.kpiThird !== undefined && target.kpiThird !== null && String(target.kpiThird) !== "")
        return String(target.kpiThird)
      var r = target.resources
      return (r && r.third !== undefined) ? String(r.third) : "—"
    }
    readonly property string kpiThirdLabel: {
      if (target.kpiThirdLabel !== undefined && target.kpiThirdLabel !== null && String(target.kpiThirdLabel) !== "")
        return String(target.kpiThirdLabel)
      var r = target.resources
      return (r && r.thirdLabel) ? String(r.thirdLabel) : "PIDs"
    }

    implicitHeight: inner.implicitHeight + Style.space(4)
    width: parent ? parent.width : 0
    opacity: busy ? 0.6 : 1.0

    Column {
      id: inner
      anchors.left: parent.left
      anchors.right: parent.right
      spacing: Style.space(4)

      Row {
        width: parent.width
        spacing: Style.space(8)

        // Title: click opens URL when present (optional default).
        Item {
          width: Math.max(40, parent.width - actionsBtn.width - Style.space(8))
          height: Math.max(titleCol.implicitHeight, actionsBtn.height)

          Column {
            id: titleCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(1)

            Row {
              spacing: Style.space(6)
              width: parent.width

              StateLed {
                anchors.verticalCenter: parent.verticalCenter
                ledState: String(target.state || "")
                hasError: !!(target.error)
              }

              Text {
                id: titleLabel
                text: row.titleText
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
                elide: Text.ElideRight
                width: Math.min(
                  implicitWidth,
                  parent.width - Style.space(6) - Style.space(6) - stateBadge.width - Style.space(6)
                )
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: stateBadge
                text: root.stateLabel(target.state)
                color: root.stateColor(String(target.state || ""), !!(target.error))
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
                font.letterSpacing: Style.font.caption * 0.12
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            StateMeter {
              width: parent.width
              implicitHeight: Style.space(3)
              percent: root.stateMeterPercent(String(target.state || ""))
              fillColor: root.stateColor(String(target.state || ""), !!(target.error))
            }

            // Three evenly spaced KPIs under the accent meter (CPU · MEM · PIDs).
            Row {
              id: kpiRow
              width: parent.width
              spacing: Style.space(4)
              visible: row.showResources

              ResourceKpi {
                width: Math.floor((kpiRow.width - kpiRow.spacing * 2) / 3)
                label: "CPU"
                value: row.kpiCpu
              }
              ResourceKpi {
                width: Math.floor((kpiRow.width - kpiRow.spacing * 2) / 3)
                label: "MEM"
                value: row.kpiMem
              }
              ResourceKpi {
                width: Math.max(0, kpiRow.width - 2 * Math.floor((kpiRow.width - kpiRow.spacing * 2) / 3) - kpiRow.spacing * 2)
                label: row.kpiThirdLabel
                value: row.kpiThird
              }
            }

            Text {
              visible: !!(target.error)
              width: parent.width
              text: String(target.error || "")
              color: Color.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }
          }

          MouseArea {
            anchors.fill: parent
            enabled: row.hasUrl
            cursorShape: row.hasUrl ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: if (row.hasUrl) root.openUrl(target.url)
          }
        }

        Button {
          id: actionsBtn
          text: row.menuOpen ? "Actions ▴" : "Actions ▾"
          fontSize: Style.font.bodySmall
          foreground: root.foreground
          fontFamily: root.fontFamily
          bordered: true
          selected: row.menuOpen
          enabled: !row.busy && row.menuEntries.length > 0
          opacity: (!row.busy && row.menuEntries.length > 0) ? 1.0 : 0.45
          anchors.verticalCenter: parent.verticalCenter
          onClicked: row.menuOpen = !row.menuOpen
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(2)
        visible: row.menuOpen && row.menuEntries.length > 0

        Repeater {
          model: row.menuEntries

          MenuAction {
            required property var modelData
            label: modelData.label
            onActivated: {
              var e = modelData
              if (e.kind === "action") root.runAction(target.id, e.id)
              else if (e.kind === "open") root.openUrl(target.url)
              else if (e.kind === "docker-tui") root.launchDockerTui()
              else if (e.kind === "ignore") root.ignoreTarget(target.id)
              else if (e.kind === "autostart") root.setAutostart(target.id, e.id === "on")
              row.menuOpen = false
            }
          }
        }
      }
    }
  }

  component MenuAction: CursorSurface {
    property string label: ""
    signal activated()
    width: parent ? parent.width : 0
    implicitHeight: Style.space(28)
    foreground: root.foreground
    fill: root.hoverFill
    currentFill: root.selectedFill
    hasCursor: false
    bordered: true
    Text {
      anchors.left: parent.left
      anchors.leftMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      text: label
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
    }
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: activated()
    }
  }
}
