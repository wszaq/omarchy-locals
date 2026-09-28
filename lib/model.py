"""Pure status model for wszaq.locals.

Maps config + probe results to status JSON. No docker, no QML, no subprocess.
"""

from __future__ import annotations

SCHEMA_VERSION = 1
SUPPORTED_KINDS = frozenset({"docker", "port"})
DEFERRED_KINDS = frozenset({"process", "compose", "systemd"})
STATES = frozenset({"running", "paused", "stopped", "unknown"})
GROUPS = frozenset({"container", "localhost", "port"})

DOCKER_ACTIONS = {
    "running": ("pause", "stop", "restart"),
    "paused": ("resume", "stop", "restart"),
    "stopped": ("start", "restart"),
    "unknown": (),
}

# Host listeners with a known stoppable PID: Stop/Pause/Resume.
# Restart is appended only when probes report can_restart (cmdline+cwd readable).
# Start is appended only when a saved recipe exists (see lib/persist.py annotate).
PROCESS_ACTIONS = {
    "running": ("pause", "stop"),
    "paused": ("resume", "stop"),
    "stopped": (),
    "unknown": (),
}

PRIMARY_BY_STATE = {
    "running": "pause",
    "paused": "resume",
    "stopped": "start",
    "unknown": None,
}

# System / service listeners that must stay Open/Ignore only (never signal).
# Matched on basename of ss `comm`, case-insensitive. docker-proxy is also
# blocked separately via docker_backed.
PROCESS_DENYLIST = frozenset(
    {
        "docker-proxy",
        "dockerd",
        "docker",
        "containerd",
        "containerd-shim",
        "containerd-shim-runc-v2",
        "sshd",
        "ssh",
        "systemd",
        "systemd-resolved",
        "systemd-logind",
        "systemd-networkd",
        "systemd-journald",
        "cupsd",
        "cups-browsed",
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "pulseaudio",
        "dbus-daemon",
        "dbus-broker",
        "networkmanager",
        "bluetoothd",
        "avahi-daemon",
        "chronyd",
        "ntpd",
        "snapd",
        "rsyslogd",
        "login",
        "getty",
        "agetty",
        "xorg",
        "xwayland",
        "hyprland",
        "sddm",
        "gdm",
        "gdm-session-worker",
        "rtkit-daemon",
        "polkitd",
        "udisksd",
        "upowerd",
        "wpa_supplicant",
        "iwd",
        "tailscaled",
        "firewalld",
        "nft",
        "master",  # postfix
        "pickup",
        "qmgr",
    }
)

# Ports that usually speak HTTP(S) — used to attach Open URL on discovery.
HTTPISH_PORTS = frozenset(
    {
        80,
        443,
        3000,
        3001,
        4000,
        4173,
        4200,
        5000,
        5173,
        8000,
        8080,
        8081,
        8443,
        8888,
        9000,
        9090,
        11434,
    }
)
HTTPISH_COMMS = frozenset(
    {
        "node",
        "nodejs",
        "nginx",
        "caddy",
        "apache2",
        "httpd",
        "python",
        "python3",
        "uvicorn",
        "granian",
    }
)

# Process names that look like local app servers → Localhosts group.
LOCALHOST_COMMS = frozenset(
    {
        "node",
        "nodejs",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "deno",
        "python",
        "python3",
        "uvicorn",
        "gunicorn",
        "granian",
        "vite",
        "next",
        "next-server",
        "nuxt",
        "astro",
        "webpack",
        "webpack-dev-server",
        "ollama",
        "ollama_llama_server",
        "nginx",
        "caddy",
        "apache2",
        "httpd",
        "ruby",
        "rails",
        "puma",
        "php",
        "php-fpm",
        "code-server",
        "hugo",
        "jekyll",
        "uvicorn",
        "fastapi",
        "django",
    }
)

# Explicit single ports treated as local apps even without an HTTP guess.
LOCALHOST_PORTS = frozenset(
    {
        5173,
        4173,
        4200,
        5000,
        8080,
        8081,
        8443,
        8888,
        9000,
        9090,
        11434,
        80,
        443,
    }
)

DEFAULT_FILTERS = {
    "showContainers": True,
    "showLocalhosts": True,
    "showPorts": False,
}

SORT_MODES = frozenset({"default", "az", "port"})
DEFAULT_SORT_MODE = "default"

_CONTAINER_STATE_ORDER = {
    "running": 0,
    "paused": 1,
    "stopped": 2,
    "unknown": 3,
}


def parse_ignore(items: list | None) -> tuple[set[str], set[int], list[str]]:
    """Split ignore entries into docker names and port numbers.

    Forms: "name", "docker:name", "53", "port:53".
    """
    errors: list[str] = []
    docker: set[str] = set()
    ports: set[int] = set()
    if items is None:
        return docker, ports, errors
    if not isinstance(items, list):
        return docker, ports, ["ignore must be an array"]
    for i, item in enumerate(items):
        raw = str(item if item is not None else "").strip()
        if not raw:
            errors.append(f"ignore[{i}] empty")
            continue
        lower = raw.lower()
        if lower.startswith("docker:"):
            name = raw.split(":", 1)[1].strip()
            if not name:
                errors.append(f"ignore[{i}] empty docker name")
                continue
            docker.add(name)
            continue
        if lower.startswith("port:"):
            part = raw.split(":", 1)[1].strip()
            try:
                port_n = int(part)
            except ValueError:
                errors.append(f"ignore[{i}] bad port {raw!r}")
                continue
            if port_n < 1 or port_n > 65535:
                errors.append(f"ignore[{i}] port out of range")
                continue
            ports.add(port_n)
            continue
        if raw.isdigit():
            port_n = int(raw)
            if port_n < 1 or port_n > 65535:
                errors.append(f"ignore[{i}] port out of range")
                continue
            ports.add(port_n)
            continue
        docker.add(raw)
    return docker, ports, errors


def guess_http_url(port: int, comm: str | None = None) -> str | None:
    """Return an http(s) URL for likely web listeners, else None."""
    try:
        port_n = int(port)
    except (TypeError, ValueError):
        return None
    comm_l = (comm or "").strip().lower()
    if port_n not in HTTPISH_PORTS and comm_l not in HTTPISH_COMMS:
        return None
    scheme = "https" if port_n in (443, 8443) else "http"
    return f"{scheme}://127.0.0.1:{port_n}"


def port_in_localhost_ranges(port: int) -> bool:
    """True for common local-app port ranges / singles."""
    try:
        port_n = int(port)
    except (TypeError, ValueError):
        return False
    if 3000 <= port_n <= 3999:
        return True
    if 8000 <= port_n <= 8999:
        return True
    return port_n in LOCALHOST_PORTS


def is_localhost_comm(comm: str | None) -> bool:
    return (comm or "").strip().lower() in LOCALHOST_COMMS


def classify_group(
    *,
    kind: str,
    port: int | None = None,
    comm: str | None = None,
    url: str | None = None,
    discovered: bool = False,
    pinned: bool | None = None,
) -> str:
    """Assign container | localhost | port.

    - Docker → container
    - Pinned port targets → localhost (intentional apps)
    - HTTP-openable / common app ports / user-app process names → localhost
    - Everything else → port
    """
    if kind == "docker":
        return "container"
    is_pinned = (not discovered) if pinned is None else bool(pinned)
    if is_pinned:
        return "localhost"
    if url:
        return "localhost"
    if port is not None and guess_http_url(port, comm):
        return "localhost"
    if port is not None and port_in_localhost_ranges(port):
        return "localhost"
    if is_localhost_comm(comm):
        return "localhost"
    return "port"


def load_targets(raw: dict | None) -> tuple[list[dict], set[str], set[int], list[str]]:
    """Parse targets.json.

    Returns (pinned_targets, ignore_docker, ignore_ports, config_errors).
    Missing config (raw is None) is plug-and-play: empty pins/ignore, no errors.
    """
    errors: list[str] = []
    if raw is None:
        return [], set(), set(), []
    if not isinstance(raw, dict):
        return [], set(), set(), ["config root must be an object"]

    ignore_docker, ignore_ports, ignore_errors = parse_ignore(raw.get("ignore", []))
    errors.extend(ignore_errors)

    items = raw.get("targets", [])
    if items is None:
        items = []
    if not isinstance(items, list):
        return [], ignore_docker, ignore_ports, errors + ["targets must be an array"]

    seen: set[str] = set()
    out: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"targets[{i}] must be an object")
            continue
        tid = str(item.get("id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not tid:
            errors.append(f"targets[{i}] missing id")
            continue
        if tid in seen:
            errors.append(f"duplicate id {tid!r}")
            continue
        seen.add(tid)
        if kind in DEFERRED_KINDS:
            errors.append(f"{tid}: kind {kind!r} deferred in v1")
            continue
        if kind not in SUPPORTED_KINDS:
            errors.append(f"{tid}: unsupported kind {kind!r}")
            continue
        label = str(item.get("label") or tid).strip() or tid
        target: dict = {
            "id": tid,
            "kind": kind,
            "label": label,
            "url": str(item.get("url") or "").strip() or None,
            "discovered": False,
        }
        if kind == "docker":
            container = str(item.get("container") or "").strip()
            if not container:
                errors.append(f"{tid}: docker target needs container")
                continue
            target["container"] = container
        elif kind == "port":
            port = item.get("port")
            try:
                port_n = int(port)
            except (TypeError, ValueError):
                errors.append(f"{tid}: port target needs integer port")
                continue
            if port_n < 1 or port_n > 65535:
                errors.append(f"{tid}: port out of range")
                continue
            target["port"] = port_n
        out.append(target)
    return out, ignore_docker, ignore_ports, errors


def discovered_docker_targets(
    containers: list[dict],
    *,
    ignore: set[str] | list[str] | None = None,
    pinned_containers: set[str] | list[str] | None = None,
) -> list[dict]:
    """Build docker target rows from docker ps discovery (stable ids)."""
    ignore_set = {str(n).strip() for n in (ignore or []) if str(n).strip()}
    pinned = {str(n).strip() for n in (pinned_containers or []) if str(n).strip()}
    out: list[dict] = []
    seen_names: set[str] = set()
    for c in containers:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        if name in ignore_set or name in pinned:
            continue
        out.append(
            {
                "id": f"docker:{name}",
                "kind": "docker",
                "label": name,
                "url": None,
                "container": name,
                "discovered": True,
            }
        )
    return out


def discovered_port_targets(
    listeners: list[dict],
    *,
    ignore_ports: set[int] | list[int] | None = None,
    pinned_ports: set[int] | list[int] | None = None,
) -> list[dict]:
    """Build status-only port rows from loopback/wildcard listeners.

    Skips docker-proxy (container row owns that publish) and ignored/pinned ports.
    """
    ignore_set = {int(p) for p in (ignore_ports or [])}
    pinned = {int(p) for p in (pinned_ports or [])}
    out: list[dict] = []
    seen: set[int] = set()
    for entry in listeners:
        if not isinstance(entry, dict):
            continue
        try:
            port = int(entry.get("port"))
        except (TypeError, ValueError):
            continue
        if port < 1 or port > 65535 or port in seen:
            continue
        if entry.get("docker_backed"):
            continue
        if port in ignore_set or port in pinned:
            continue
        seen.add(port)
        comm = entry.get("comm")
        url = guess_http_url(port, str(comm) if comm else None)
        out.append(
            {
                "id": f"port:{port}",
                "kind": "port",
                "label": f":{port}",
                "url": url,
                "port": port,
                "discovered": True,
            }
        )
    return out


def merge_targets(
    pinned: list[dict],
    discovered_containers: list[dict],
    discovered_listeners: list[dict],
    *,
    ignore_docker: set[str] | list[str] | None = None,
    ignore_ports: set[int] | list[int] | None = None,
) -> list[dict]:
    """Pinned first, then auto-discovered ports, then auto-discovered docker."""
    pinned_containers = [t["container"] for t in pinned if t.get("kind") == "docker"]
    pinned_ports = [t["port"] for t in pinned if t.get("kind") == "port"]
    auto_ports = discovered_port_targets(
        discovered_listeners,
        ignore_ports=ignore_ports,
        pinned_ports=pinned_ports,
    )
    auto_docker = discovered_docker_targets(
        discovered_containers,
        ignore=ignore_docker,
        pinned_containers=pinned_containers,
    )
    return list(pinned) + auto_ports + auto_docker


def docker_actions_for(state: str) -> list[str]:
    return list(DOCKER_ACTIONS.get(state, ()))


def process_actions_for(state: str, *, can_restart: bool = False) -> list[str]:
    actions = list(PROCESS_ACTIONS.get(state, ()))
    if can_restart and state in ("running", "paused") and "restart" not in actions:
        actions.append("restart")
    return actions


def _comm_basename(comm: str | None) -> str:
    raw = (comm or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    return raw.lower()


def is_process_controllable(
    *,
    comm: str | None = None,
    pid: int | None = None,
    docker_backed: bool = False,
) -> bool:
    """True when a host listener may receive Stop/Pause/Resume/Restart.

    Never for docker-proxy / docker_backed (container row owns that),
    missing/invalid pid, or denylisted system daemons.
    """
    if docker_backed:
        return False
    if pid is None:
        return False
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_n <= 1:
        return False
    name = _comm_basename(comm)
    if not name or name in PROCESS_DENYLIST:
        return False
    return True


def primary_action(state: str, actions: list[str]) -> str | None:
    candidate = PRIMARY_BY_STATE.get(state)
    if candidate and candidate in actions:
        return candidate
    return None


def build_target_status(
    target: dict,
    *,
    docker_reachable: bool,
    docker_probe: dict | None = None,
    port_probe: dict | None = None,
) -> dict:
    """Build one target status record from probe results."""
    kind = target["kind"]
    base = {
        "id": target["id"],
        "kind": kind,
        "label": target["label"],
        "url": target.get("url"),
        "state": "unknown",
        "actions": [],
        "primary": None,
        "error": None,
        "meta": {},
        "statusOnly": kind == "port",
        "discovered": bool(target.get("discovered")),
        "group": "container" if kind == "docker" else "port",
    }

    if kind == "port":
        port = target["port"]
        base["meta"] = {"port": port}
        probe = port_probe or {}
        if probe.get("error"):
            base["state"] = "unknown"
            base["error"] = str(probe["error"])
            base["group"] = classify_group(
                kind="port",
                port=port,
                comm=None,
                url=base.get("url"),
                discovered=bool(target.get("discovered")),
            )
            _attach_resources(base, probe)
            return base
        listening = bool(probe.get("listening"))
        paused = bool(probe.get("paused"))
        if listening and paused:
            state = "paused"
        elif listening:
            state = "running"
        else:
            state = "stopped"
        base["state"] = state
        if probe.get("comm"):
            base["meta"]["comm"] = probe["comm"]
        pid = probe.get("pid")
        if pid is not None:
            try:
                base["meta"]["pid"] = int(pid)
            except (TypeError, ValueError):
                pid = None
        docker_backed = bool(probe.get("docker_backed"))
        if docker_backed:
            base["meta"]["dockerBacked"] = True
        can_restart = bool(probe.get("can_restart"))
        if can_restart:
            base["meta"]["canRestart"] = True
        controllable = is_process_controllable(
            comm=probe.get("comm"),
            pid=base["meta"].get("pid"),
            docker_backed=docker_backed,
        )
        if controllable and state in ("running", "paused"):
            actions = process_actions_for(state, can_restart=can_restart)
        else:
            actions = []
        base["actions"] = actions
        base["primary"] = primary_action(state, actions)
        base["statusOnly"] = len(actions) == 0
        # Prefer explicit pin URL; else keep discovery guess; else derive from probe.
        if not base["url"]:
            base["url"] = guess_http_url(port, probe.get("comm"))
        base["group"] = classify_group(
            kind="port",
            port=port,
            comm=probe.get("comm"),
            url=base.get("url"),
            discovered=bool(target.get("discovered")),
        )
        _attach_resources(base, probe)
        return base

    # docker
    container = target["container"]
    base["meta"] = {"container": container}
    base["group"] = "container"
    base["statusOnly"] = False
    if not docker_reachable:
        base["state"] = "unknown"
        base["error"] = "docker unavailable"
        _attach_resources(base, docker_probe)
        return base
    probe = docker_probe or {}
    if probe.get("error"):
        base["state"] = "unknown"
        base["error"] = str(probe["error"])
        _attach_resources(base, probe)
        return base
    state = str(probe.get("state") or "unknown")
    if state not in STATES:
        state = "unknown"
    base["state"] = state
    actions = docker_actions_for(state)
    base["actions"] = actions
    base["primary"] = primary_action(state, actions)
    _attach_resources(base, probe)
    return base


def _attach_resources(row: dict, probe: dict | None) -> None:
    """Copy ready-to-render resources from a probe onto a status row."""
    if not isinstance(probe, dict):
        return
    resources = probe.get("resources")
    if not isinstance(resources, dict):
        return
    # Require at least one display field so UI can hide empty KPI rows.
    if not any(resources.get(k) for k in ("cpu", "mem", "third")):
        return
    cpu = str(resources.get("cpu") or "—")
    mem = str(resources.get("mem") or "—")
    third = str(resources.get("third") or "—")
    third_label = str(resources.get("thirdLabel") or "PIDs")
    payload = {
        "cpu": cpu,
        "mem": mem,
        "memBytes": resources.get("memBytes"),
        "third": third,
        "thirdLabel": third_label,
    }
    row["resources"] = payload
    # Flat mirrors for QML (avoids QObject.resources name collision on some hosts).
    row["kpiCpu"] = cpu
    row["kpiMem"] = mem
    row["kpiThird"] = third
    row["kpiThirdLabel"] = third_label
    row["hasResourceKpis"] = True


def action_allowed(target_status: dict, action: str) -> bool:
    return action in (target_status.get("actions") or [])


def ignore_token_for(row: dict) -> str | None:
    """Return the ignore-list token for a status/target row, or None."""
    kind = row.get("kind")
    if kind == "docker":
        name = (row.get("meta") or {}).get("container") or row.get("container")
        name = str(name or "").strip()
        return f"docker:{name}" if name else None
    if kind == "port":
        port = (row.get("meta") or {}).get("port")
        if port is None:
            port = row.get("port")
        try:
            port_n = int(port)
        except (TypeError, ValueError):
            return None
        return f"port:{port_n}"
    return None


def normalize_filters(filters: dict | None = None) -> dict:
    """Merge caller filters onto defaults (Containers/Localhosts on, Ports off)."""
    out = dict(DEFAULT_FILTERS)
    if not filters:
        return out
    for key in ("showContainers", "showLocalhosts", "showPorts"):
        if key in filters and filters[key] is not None:
            out[key] = bool(filters[key])
    return out


def normalize_sort_mode(mode: str | None = None) -> str:
    """Accept default | az | port (aliases: a-z, alpha, name → az)."""
    raw = str(mode if mode is not None else DEFAULT_SORT_MODE).strip().lower()
    if raw in ("a-z", "alpha", "name", "label"):
        return "az"
    if raw in SORT_MODES:
        return raw
    return DEFAULT_SORT_MODE


def _row_port(row: dict) -> int:
    meta = row.get("meta") or {}
    try:
        return int(meta.get("port") if meta.get("port") is not None else row.get("port") or 0)
    except (TypeError, ValueError):
        return 0


def sort_containers(rows: list[dict], mode: str | None = None) -> list[dict]:
    """Sort container rows. default = state then name; az; port (name fallback)."""
    m = normalize_sort_mode(mode)
    if m == "az":
        return sorted(
            rows,
            key=lambda r: (
                str(r.get("label") or "").lower(),
                str(r.get("id") or ""),
            ),
        )
    if m == "port":
        return sorted(
            rows,
            key=lambda r: (
                _row_port(r),
                str(r.get("label") or "").lower(),
                str(r.get("id") or ""),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            _CONTAINER_STATE_ORDER.get(str(r.get("state") or "unknown"), 9),
            str(r.get("label") or "").lower(),
            str(r.get("id") or ""),
        ),
    )


def sort_localhosts(rows: list[dict], mode: str | None = None) -> list[dict]:
    """Sort localhost rows. default = up first then port; az; port."""
    m = normalize_sort_mode(mode)
    if m == "az":
        return sorted(
            rows,
            key=lambda r: (
                str(r.get("label") or "").lower(),
                str(r.get("id") or ""),
            ),
        )
    if m == "port":
        return sorted(
            rows,
            key=lambda r: (
                _row_port(r),
                str(r.get("label") or "").lower(),
                str(r.get("id") or ""),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            0 if r.get("state") == "running" else 1,
            _row_port(r),
            str(r.get("label") or "").lower(),
            str(r.get("id") or ""),
        ),
    )


def sort_ports(rows: list[dict], mode: str | None = None) -> list[dict]:
    """Sort port rows. default/port = port ascending; az = label."""
    m = normalize_sort_mode(mode)
    if m == "az":
        return sorted(
            rows,
            key=lambda r: (
                str(r.get("label") or "").lower(),
                str(r.get("id") or ""),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            _row_port(r),
            str(r.get("label") or "").lower(),
            str(r.get("id") or ""),
        ),
    )


def group_rows(rows: list[dict], sort_mode: str | None = None) -> dict[str, list[dict]]:
    """Split status rows into sorted Containers / Localhosts / Ports."""
    mode = normalize_sort_mode(sort_mode)
    containers: list[dict] = []
    localhosts: list[dict] = []
    ports: list[dict] = []
    for r in rows:
        group = r.get("group")
        if group not in GROUPS:
            group = classify_group(
                kind=str(r.get("kind") or ""),
                port=_row_port(r) or None,
                comm=(r.get("meta") or {}).get("comm"),
                url=r.get("url"),
                discovered=bool(r.get("discovered")),
            )
            r = dict(r)
            r["group"] = group
        if group == "container":
            containers.append(r)
        elif group == "localhost":
            localhosts.append(r)
        else:
            ports.append(r)
    return {
        "containers": sort_containers(containers, mode),
        "localhosts": sort_localhosts(localhosts, mode),
        "ports": sort_ports(ports, mode),
    }


def filter_rows(rows: list[dict], filters: dict | None = None) -> list[dict]:
    """Keep rows whose group is switched on."""
    f = normalize_filters(filters)
    out: list[dict] = []
    for r in rows:
        group = r.get("group")
        if group == "container" and f["showContainers"]:
            out.append(r)
        elif group == "localhost" and f["showLocalhosts"]:
            out.append(r)
        elif group == "port" and f["showPorts"]:
            out.append(r)
    return out


def filter_groups(groups: dict[str, list[dict]], filters: dict | None = None) -> dict[str, list[dict]]:
    f = normalize_filters(filters)
    return {
        "containers": list(groups.get("containers") or []) if f["showContainers"] else [],
        "localhosts": list(groups.get("localhosts") or []) if f["showLocalhosts"] else [],
        "ports": list(groups.get("ports") or []) if f["showPorts"] else [],
    }


def counts_for_bar(rows: list[dict], filters: dict | None = None) -> dict:
    """Bar digit / header counts for visible (filtered) rows.

    running = running docker + non-docker-proxy host listeners.
    paused = docker pause + host SIGSTOP.
    """
    visible = filter_rows(rows, filters)
    running = 0
    paused = 0
    unknown = 0
    for r in visible:
        kind = r.get("kind")
        state = r.get("state")
        if kind == "docker":
            if state == "running":
                running += 1
            elif state == "paused":
                paused += 1
            elif state == "unknown":
                unknown += 1
        elif kind == "port":
            if (r.get("meta") or {}).get("dockerBacked"):
                continue
            if state == "running":
                running += 1
            elif state == "paused":
                paused += 1
            elif state == "unknown":
                unknown += 1
    return {
        "total": len(visible),
        "running": running,
        "paused": paused,
        "unknown": unknown,
    }


def build_status(
    targets: list[dict],
    *,
    docker_reachable: bool,
    docker_probes: dict[str, dict] | None = None,
    port_probes: dict[str, dict] | None = None,
    config_errors: list[str] | None = None,
    config_path: str | None = None,
    probed_at: str | None = None,
    filters: dict | None = None,
    sort_mode: str | None = None,
) -> dict:
    docker_probes = docker_probes or {}
    port_probes = port_probes or {}
    rows = []
    for t in targets:
        if t["kind"] == "docker":
            rows.append(
                build_target_status(
                    t,
                    docker_reachable=docker_reachable,
                    docker_probe=docker_probes.get(t["id"]),
                )
            )
        else:
            rows.append(
                build_target_status(
                    t,
                    docker_reachable=docker_reachable,
                    port_probe=port_probes.get(t["id"]),
                )
            )

    active_sort = normalize_sort_mode(sort_mode)
    groups = group_rows(rows, active_sort)
    # Stable panel order: containers, localhosts, ports (each already sorted).
    ordered = groups["containers"] + groups["localhosts"] + groups["ports"]
    active_filters = normalize_filters(filters)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "docker": {"reachable": bool(docker_reachable)},
        "configPath": config_path,
        "probedAt": probed_at,
        "filters": active_filters,
        "sortMode": active_sort,
        "counts": counts_for_bar(ordered, active_filters),
        "configErrors": list(config_errors or []),
        "groups": groups,
        "targets": ordered,
    }
