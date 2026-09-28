"""Side-effect probes for wszaq.locals (stdlib only)."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

STDERR_CAP = 4096
DEFAULT_TIMEOUT = 3.0

_SS_LISTEN_RE = re.compile(
    r"LISTEN\s+\S+\s+\S+\s+(\S+)\s+\S+(?:\s+users:\((.+)\))?"
)
_SS_USER_RE = re.compile(r'\("([^"]+)",pid=(\d+)')

# Loopback + wildcard — reachable via localhost. LAN-only binds are skipped.
_LOCALHOST_HOSTS = frozenset(
    {
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "*",
        "::",
        "[::]",
        "[::1]",
    }
)


def _cap(text: str | bytes | None, limit: int = STDERR_CAP) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = text.strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def run_cmd(
    argv: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    env: dict | None = None,
) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        return proc.returncode, _cap(proc.stdout), _cap(proc.stderr)
    except FileNotFoundError:
        return 127, "", f"not found: {argv[0]}"
    except subprocess.TimeoutExpired as exc:
        return 124, _cap(exc.stdout), _cap(exc.stderr) or "timeout"


def docker_reachable(run: Callable = run_cmd) -> bool:
    # Prefer socket existence check first — cheap and works when daemon is down.
    sock = Path("/var/run/docker.sock")
    if not sock.exists():
        # Still try CLI in case of alternate context, but treat miss as down.
        code, _, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=2.0)
        return code == 0
    code, _, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=2.0)
    return code == 0


def _normalize_container_name(name: str) -> str:
    name = (name or "").strip()
    if "," in name:
        name = name.split(",", 1)[0].strip()
    if name.startswith("/"):
        name = name[1:]
    return name


def _map_docker_ps_state(raw: str) -> str:
    state = (raw or "").strip().lower()
    if state == "paused":
        return "paused"
    if state == "running":
        return "running"
    if state in ("exited", "created", "dead"):
        return "stopped"
    return "unknown"


def list_docker_containers(run: Callable = run_cmd) -> dict:
    """List all containers via `docker ps -a` JSON lines.

    Returns {"ok": bool, "error": str|None, "containers": [{name, id, state}]}.
    """
    code, out, err = run(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        timeout=DEFAULT_TIMEOUT,
    )
    if code != 0:
        return {
            "ok": False,
            "error": err or out or f"docker ps failed ({code})",
            "containers": [],
        }
    containers: list[dict] = []
    seen: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = _normalize_container_name(str(obj.get("Names") or ""))
        if not name or name in seen:
            continue
        seen.add(name)
        cid = str(obj.get("ID") or "")[:12]
        containers.append(
            {
                "name": name,
                "id": cid,
                "state": _map_docker_ps_state(str(obj.get("State") or "")),
            }
        )
    return {"ok": True, "error": None, "containers": containers}


def probe_docker_container(name: str, run: Callable = run_cmd) -> dict:
    code, out, err = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            name,
        ],
        timeout=DEFAULT_TIMEOUT,
    )
    if code != 0:
        msg = err or out or f"docker inspect failed ({code})"
        if "No such object" in msg or "no such object" in msg.lower():
            return {"state": "stopped", "error": None}
        return {"state": "unknown", "error": msg}
    try:
        state = json.loads(out)
    except json.JSONDecodeError:
        return {"state": "unknown", "error": "bad docker inspect json"}
    if not isinstance(state, dict):
        return {"state": "unknown", "error": "bad docker state"}
    if state.get("Paused"):
        return {"state": "paused", "error": None}
    if state.get("Running"):
        return {"state": "running", "error": None}
    return {"state": "stopped", "error": None}


def _addr_port(local: str) -> int | None:
    # [::1]:8080 or 127.0.0.1:8080 or *:8080
    if local.startswith("["):
        m = re.search(r"\]:(\d+)$", local)
        return int(m.group(1)) if m else None
    if ":" in local:
        try:
            return int(local.rsplit(":", 1)[-1])
        except ValueError:
            return None
    return None


def _addr_host(local: str) -> str:
    if local.startswith("["):
        m = re.match(r"^(\[[^\]]+\])", local)
        return m.group(1) if m else local
    if ":" in local:
        return local.rsplit(":", 1)[0]
    return local


def _is_localhost_bind(local: str) -> bool:
    host = _addr_host(local)
    if host in _LOCALHOST_HOSTS:
        return True
    # Some ss builds print [::]:port without brackets in host split — handled above.
    return False


def _parse_ss_users(users: str) -> tuple[str | None, int | None]:
    um = _SS_USER_RE.search(users or "")
    if not um:
        return None, None
    return um.group(1), int(um.group(2))


def list_listening_ports(run: Callable = run_cmd) -> dict:
    """Parse `ss -ltnp` into listener records.

    Returns {
      ok, error,
      listeners: [{port, addr, comm, pid, docker_backed, localhost}],
    }
    One record per port (first match wins); localhost flag marks loopback/wildcard.
    """
    code, out, err = run(["ss", "-ltnp"], timeout=DEFAULT_TIMEOUT)
    if code != 0:
        return {
            "ok": False,
            "error": err or f"ss failed ({code})",
            "listeners": [],
        }
    by_port: dict[int, dict] = {}
    for line in out.splitlines():
        m = _SS_LISTEN_RE.search(line)
        if not m:
            continue
        local = m.group(1)
        port = _addr_port(local)
        if port is None:
            continue
        comm, pid = _parse_ss_users(m.group(2) or "")
        docker_backed = (comm or "") == "docker-proxy"
        localhost = _is_localhost_bind(local)
        existing = by_port.get(port)
        if existing is None:
            by_port[port] = {
                "port": port,
                "addr": local,
                "comm": comm,
                "pid": pid,
                "docker_backed": docker_backed,
                "localhost": localhost,
            }
            continue
        # Prefer a localhost bind representation; keep docker_backed if any bind is.
        if localhost and not existing.get("localhost"):
            existing["addr"] = local
            existing["localhost"] = True
        if docker_backed:
            existing["docker_backed"] = True
        if existing.get("comm") is None and comm:
            existing["comm"] = comm
            existing["pid"] = pid
    return {"ok": True, "error": None, "listeners": list(by_port.values())}


def probe_port(port: int, run: Callable = run_cmd, listeners: list[dict] | None = None) -> dict:
    """Check whether `port` is listening. Optionally reuse a prior ss listing.

    When a PID is present, enrich with paused (SIGSTOP) and can_restart
    (same-user cmdline+cwd readable for re-exec).
    """
    if listeners is None:
        listing = list_listening_ports(run=run)
        if not listing["ok"]:
            return {"listening": False, "error": listing["error"]}
        listeners = listing["listeners"]
    for entry in listeners:
        if int(entry.get("port") or -1) != int(port):
            continue
        pid = entry.get("pid")
        info = process_snapshot(pid) if pid is not None else {}
        return {
            "listening": True,
            "comm": entry.get("comm"),
            "pid": pid,
            "docker_backed": bool(entry.get("docker_backed")),
            "paused": bool(info.get("paused")),
            "can_restart": bool(info.get("can_restart")),
            "error": None,
        }
    return {
        "listening": False,
        "error": None,
        "docker_backed": False,
        "paused": False,
        "can_restart": False,
    }


def process_snapshot(pid: int | None) -> dict:
    """Read /proc/<pid> for pause state and restart eligibility."""
    out = {"paused": False, "can_restart": False, "alive": False, "argv": None, "cwd": None}
    try:
        pid_n = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return out
    if pid_n <= 1:
        return out
    proc = Path("/proc") / str(pid_n)
    if not proc.exists():
        return out
    out["alive"] = True
    try:
        # /proc/pid/stat: field 3 is state (T/t = stopped).
        stat = (proc / "stat").read_text(encoding="utf-8", errors="replace")
        # Comm may contain spaces inside parentheses — split after last ") ".
        close = stat.rfind(")")
        if close >= 0:
            fields = stat[close + 1 :].split()
            if fields and fields[0] in ("T", "t"):
                out["paused"] = True
    except OSError:
        pass
    try:
        me = os.getuid()
        status = (proc / "status").read_text(encoding="utf-8", errors="replace")
        uid = None
        for line in status.splitlines():
            if line.startswith("Uid:"):
                parts = line.split()
                if len(parts) >= 2:
                    uid = int(parts[1])
                break
        if uid is not None and uid != me:
            return out
    except (OSError, ValueError):
        return out
    try:
        raw = (proc / "cmdline").read_bytes()
        if not raw or raw == b"\0":
            return out
        argv = [a.decode("utf-8", errors="replace") for a in raw.split(b"\0") if a]
        if not argv:
            return out
        cwd = os.readlink(str(proc / "cwd"))
        out["argv"] = argv
        out["cwd"] = cwd
        out["can_restart"] = True
    except OSError:
        pass
    return out


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_action(pid: int, action: str) -> tuple[bool, str]:
    """Signal or re-exec a host listener PID.

    stop: SIGTERM then SIGKILL. pause: SIGSTOP. resume: SIGCONT (wake).
    restart: capture cmdline+cwd, stop, then Popen the same argv in cwd.
    Never call for docker-proxy / denylisted rows — model must gate first.
    """
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return False, "invalid pid"
    if pid_n <= 1:
        return False, "refusing pid <= 1"

    if action == "pause":
        try:
            os.kill(pid_n, signal.SIGSTOP)
            return True, "paused"
        except ProcessLookupError:
            return False, "process gone"
        except PermissionError:
            return False, "permission denied (pause)"

    if action == "resume":
        try:
            os.kill(pid_n, signal.SIGCONT)
            return True, "resumed"
        except ProcessLookupError:
            return False, "process gone"
        except PermissionError:
            return False, "permission denied (resume)"

    if action == "stop":
        try:
            os.kill(pid_n, signal.SIGTERM)
        except ProcessLookupError:
            return True, "already gone"
        except PermissionError:
            return False, "permission denied (stop)"
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not _pid_alive(pid_n):
                return True, "stopped"
            time.sleep(0.1)
        try:
            os.kill(pid_n, signal.SIGKILL)
        except ProcessLookupError:
            return True, "stopped"
        except PermissionError:
            return False, "permission denied (kill)"
        time.sleep(0.1)
        return (True, "killed") if not _pid_alive(pid_n) else (False, "still alive after SIGKILL")

    if action == "restart":
        snap = process_snapshot(pid_n)
        argv = snap.get("argv")
        cwd = snap.get("cwd")
        if not argv or not cwd:
            return False, "cannot read cmdline/cwd for restart"
        ok, detail = process_action(pid_n, "stop")
        if not ok:
            return False, detail
        return start_from_recipe(argv, cwd)

    return False, f"unknown process action {action!r}"


def start_from_recipe(argv: list[str], cwd: str) -> tuple[bool, str]:
    """Spawn argv in cwd (used by Restart and post-login Start)."""
    if not argv or not cwd:
        return False, "argv/cwd required"
    try:
        subprocess.Popen(  # noqa: S603 — intentional re-exec of same-user process
            list(argv),
            cwd=str(cwd),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return True, "started"
    except OSError as exc:
        return False, f"start failed: {exc}"


def docker_action(container: str, action: str, run: Callable = run_cmd) -> tuple[bool, str]:
    mapping = {
        "start": ["docker", "start", container],
        "stop": ["docker", "stop", container],
        "restart": ["docker", "restart", container],
        "pause": ["docker", "pause", container],
        "resume": ["docker", "unpause", container],
    }
    argv = mapping.get(action)
    if not argv:
        return False, f"unknown action {action!r}"
    code, out, err = run(argv, timeout=60.0)
    if code != 0:
        return False, err or out or f"docker {action} failed ({code})"
    return True, out or "ok"


def docker_start_with_retry(
    container: str,
    *,
    attempts: int = 6,
    delay_sec: float = 2.0,
    run: Callable = run_cmd,
) -> tuple[bool, str]:
    """Start a container, retrying while the daemon is still coming up."""
    last = "not attempted"
    for i in range(max(1, attempts)):
        ok, detail = docker_action(container, "start", run=run)
        if ok:
            return True, detail if i == 0 else f"{detail} (attempt {i + 1})"
        last = detail
        # Daemon not ready yet — wait and retry.
        low = (detail or "").lower()
        if "cannot connect" in low or "is the docker daemon running" in low or "permission denied" in low:
            time.sleep(delay_sec)
            continue
        # Other errors (no such container) — do not spin.
        if i + 1 < attempts and ("connection" in low or "timeout" in low):
            time.sleep(delay_sec)
            continue
        break
    return False, last


def ensure_state_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_log(log_path: Path, record: dict) -> None:
    ensure_state_dir(log_path.parent)
    record = dict(record)
    record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "omarchy" / "locals" / "targets.json"


def default_state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(xdg) / "omarchy" / "locals"


def default_cpu_sample_path() -> Path:
    return default_state_dir() / "cpu-sample.json"


# --- Per-row resource KPIs (CPU · MEM · PIDs) ---------------------------------

_DASH = "—"
_DOCKER_SIZE_RE = re.compile(
    r"^\s*([\d.]+)\s*([KMGTPE]?i?B)\s*$",
    re.IGNORECASE,
)


def humanize_bytes(n: int | float | None) -> str:
    """Compact RSS for UI: 128M, 1.2G, 512K, 42B."""
    if n is None:
        return _DASH
    try:
        value = float(n)
    except (TypeError, ValueError):
        return _DASH
    if value < 0:
        return _DASH
    units = ((1 << 30, "G"), (1 << 20, "M"), (1 << 10, "K"))
    for div, suffix in units:
        if value >= div:
            scaled = value / div
            if scaled >= 10 or abs(scaled - round(scaled)) < 0.05:
                return f"{int(round(scaled))}{suffix}"
            return f"{scaled:.1f}{suffix}"
    return f"{int(round(value))}B"


def format_cpu_percent(pct: float | None) -> str:
    """One-core (or docker host) CPU share for UI: 12%, 0.1%, —."""
    if pct is None:
        return _DASH
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return _DASH
    if value < 0:
        return _DASH
    if value < 0.05:
        return "0%"
    if value < 10:
        return f"{value:.1f}%"
    return f"{int(round(value))}%"


def empty_resources(*, third_label: str = "PIDs") -> dict:
    return {
        "cpu": _DASH,
        "mem": _DASH,
        "memBytes": None,
        "third": _DASH,
        "thirdLabel": third_label,
    }


def resources_payload(
    *,
    cpu: str | None = None,
    mem: str | None = None,
    mem_bytes: int | None = None,
    third: str | None = None,
    third_label: str = "PIDs",
) -> dict:
    return {
        "cpu": cpu if cpu else _DASH,
        "mem": mem if mem else (_DASH if mem_bytes is None else humanize_bytes(mem_bytes)),
        "memBytes": mem_bytes,
        "third": third if third is not None and str(third) != "" else _DASH,
        "thirdLabel": third_label or "PIDs",
    }


def parse_docker_size(raw: str | None) -> int | None:
    """Parse docker stats size tokens like 45.2MiB, 1.23kB, 890B."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in (".", "-", "0"):
        return 0 if text == "0" else None
    m = _DOCKER_SIZE_RE.match(text)
    if not m:
        return None
    try:
        amount = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    # Docker mixes IEC (MiB) and SI-ish (kB) — treat iB as 1024, B as 1000 for k/M/G.
    multiples = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
        "ib": 1,  # rare
    }
    # Also accept bare K/M/G as binary (docker table sometimes omits i).
    if unit in ("k", "m", "g", "t"):
        unit = unit + "ib"
    mult = multiples.get(unit)
    if mult is None:
        return None
    return int(round(amount * mult))


def parse_docker_mem_usage(raw: str | None) -> int | None:
    """Extract used bytes from '45.2MiB / 7.765GiB'."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    used = text.split("/", 1)[0].strip()
    return parse_docker_size(used)


def parse_docker_cpu_perc(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().rstrip("%")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def resources_from_docker_stats(obj: dict) -> dict:
    """Map one `docker stats --format '{{json .}}'` object to UI resources."""
    cpu_pct = parse_docker_cpu_perc(obj.get("CPUPerc") if isinstance(obj, dict) else None)
    mem_bytes = parse_docker_mem_usage(obj.get("MemUsage") if isinstance(obj, dict) else None)
    pids_raw = obj.get("PIDs") if isinstance(obj, dict) else None
    third = _DASH
    if pids_raw is not None and str(pids_raw).strip() != "":
        try:
            third = str(int(str(pids_raw).strip()))
        except ValueError:
            third = str(pids_raw).strip()
    return resources_payload(
        cpu=format_cpu_percent(cpu_pct),
        mem_bytes=mem_bytes,
        third=third,
        third_label="PIDs",
    )


def list_docker_stats(run: Callable = run_cmd) -> dict:
    """Batch `docker stats --no-stream` once per poll.

    Returns {"ok", "error", "by_name": {container_name: resources}}.
    """
    code, out, err = run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        timeout=DEFAULT_TIMEOUT,
    )
    if code != 0:
        return {
            "ok": False,
            "error": err or out or f"docker stats failed ({code})",
            "by_name": {},
        }
    by_name: dict[str, dict] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = _normalize_container_name(str(obj.get("Name") or obj.get("Names") or ""))
        if not name:
            continue
        by_name[name] = resources_from_docker_stats(obj)
    return {"ok": True, "error": None, "by_name": by_name}


def _clk_tck() -> int:
    try:
        return int(os.sysconf("SC_CLK_TCK"))
    except (AttributeError, ValueError, OSError):
        return 100


def read_proc_stat_cpu(pid: int) -> tuple[int, int] | None:
    """Return (utime+stime jiffies, num_threads) from /proc/<pid>/stat."""
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_n <= 0:
        return None
    try:
        raw = (Path("/proc") / str(pid_n) / "stat").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 1 :].split()
    # After ')': state(0) … utime(11) stime(12) … num_threads(17)
    if len(fields) < 18:
        return None
    try:
        utime = int(fields[11])
        stime = int(fields[12])
        nthreads = int(fields[17])
    except ValueError:
        return None
    return utime + stime, nthreads


def read_proc_rss_bytes(pid: int) -> int | None:
    """RSS bytes from /proc/<pid>/status VmRSS."""
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_n <= 0:
        return None
    try:
        text = (Path("/proc") / str(pid_n) / "status").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1]) * 1024  # kB → bytes
                except ValueError:
                    return None
            break
    return None


def read_proc_threads(pid: int) -> int | None:
    """Thread count from status Threads: (fallback: stat num_threads)."""
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_n <= 0:
        return None
    try:
        text = (Path("/proc") / str(pid_n) / "status").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        snap = read_proc_stat_cpu(pid_n)
        return snap[1] if snap else None
    for line in text.splitlines():
        if line.startswith("Threads:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
            break
    snap = read_proc_stat_cpu(pid_n)
    return snap[1] if snap else None


def load_cpu_samples(path: Path | None = None) -> dict:
    sample_path = path or default_cpu_sample_path()
    try:
        raw = json.loads(sample_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"ts": None, "pids": {}}
    if not isinstance(raw, dict):
        return {"ts": None, "pids": {}}
    pids = raw.get("pids")
    if not isinstance(pids, dict):
        pids = {}
    return {"ts": raw.get("ts"), "pids": pids}


def save_cpu_samples(store: dict, path: Path | None = None) -> None:
    sample_path = path or default_cpu_sample_path()
    ensure_state_dir(sample_path.parent)
    payload = {"ts": store.get("ts"), "pids": store.get("pids") or {}}
    tmp = sample_path.with_suffix(sample_path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(sample_path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def cpu_percent_from_delta(
    *,
    prev_jiffies: int | None,
    prev_ts: float | None,
    cur_jiffies: int,
    cur_ts: float,
    clk_tck: int | None = None,
) -> float | None:
    """Percent of one core from consecutive /proc utime+stime samples."""
    if prev_jiffies is None or prev_ts is None:
        return None
    dt = cur_ts - float(prev_ts)
    if dt <= 0.05 or dt > 120:
        return None
    dj = cur_jiffies - int(prev_jiffies)
    if dj < 0:
        return None
    ticks = clk_tck if clk_tck is not None else _clk_tck()
    if ticks <= 0:
        return None
    return 100.0 * (dj / ticks) / dt


def sample_pid_resources(
    pid: int,
    *,
    prev: dict | None = None,
    now: float | None = None,
    clk_tck: int | None = None,
) -> tuple[dict, dict | None]:
    """Sample one host PID → (resources, next_sample_entry|None).

    next_sample_entry is {"jiffies", "ts"} to persist for the next poll.
    Third KPI is thread count, labeled PIDs (process/thread slots).
    """
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return empty_resources(), None
    snap = read_proc_stat_cpu(pid_n)
    if snap is None:
        return empty_resources(), None
    jiffies, _nthreads = snap
    ts = float(now if now is not None else time.time())
    prev_j = None
    prev_ts = None
    if isinstance(prev, dict):
        try:
            prev_j = int(prev.get("jiffies"))  # type: ignore[arg-type]
            prev_ts = float(prev.get("ts"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            prev_j = None
            prev_ts = None
    pct = cpu_percent_from_delta(
        prev_jiffies=prev_j,
        prev_ts=prev_ts,
        cur_jiffies=jiffies,
        cur_ts=ts,
        clk_tck=clk_tck,
    )
    mem_bytes = read_proc_rss_bytes(pid_n)
    threads = read_proc_threads(pid_n)
    third = str(threads) if threads is not None else _DASH
    res = resources_payload(
        cpu=format_cpu_percent(pct),
        mem_bytes=mem_bytes,
        third=third,
        third_label="PIDs",
    )
    return res, {"jiffies": jiffies, "ts": ts}


def sample_pids_resources(
    pids: list[int] | set[int],
    *,
    sample_path: Path | None = None,
    now: float | None = None,
    clk_tck: int | None = None,
) -> dict[int, dict]:
    """Batch-sample host PIDs; persists deltas to cpu-sample.json."""
    store = load_cpu_samples(sample_path)
    prev_pids = store.get("pids") if isinstance(store.get("pids"), dict) else {}
    ts = float(now if now is not None else time.time())
    out: dict[int, dict] = {}
    next_pids: dict[str, dict] = {}
    seen: set[int] = set()
    for raw_pid in pids:
        try:
            pid_n = int(raw_pid)
        except (TypeError, ValueError):
            continue
        if pid_n <= 1 or pid_n in seen:
            continue
        seen.add(pid_n)
        prev = prev_pids.get(str(pid_n))
        res, entry = sample_pid_resources(
            pid_n, prev=prev if isinstance(prev, dict) else None, now=ts, clk_tck=clk_tck
        )
        out[pid_n] = res
        if entry is not None:
            next_pids[str(pid_n)] = entry
    save_cpu_samples({"ts": ts, "pids": next_pids}, sample_path)
    return out
