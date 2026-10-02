#!/usr/bin/env python3
"""Fixture tests for wszaq.locals model (no live docker)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from lib import model, probes  # noqa: E402


class LoadTargetsTests(unittest.TestCase):
    def test_empty(self):
        targets, ign_d, ign_p, errors = model.load_targets({"targets": []})
        self.assertEqual(targets, [])
        self.assertEqual(ign_d, set())
        self.assertEqual(ign_p, set())
        self.assertEqual(errors, [])

    def test_missing_config_is_ok(self):
        targets, ign_d, ign_p, errors = model.load_targets(None)
        self.assertEqual(targets, [])
        self.assertEqual(errors, [])
        self.assertEqual(ign_d, set())
        self.assertEqual(ign_p, set())

    def test_ignore_docker_and_ports(self):
        _, ign_d, ign_p, errors = model.load_targets(
            {
                "ignore": ["postgres", "docker:redis", "53", "port:631"],
                "targets": [],
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(ign_d, {"postgres", "redis"})
        self.assertEqual(ign_p, {53, 631})

    def test_docker_and_port(self):
        targets, _, _, errors = model.load_targets(
            {
                "targets": [
                    {"id": "db", "kind": "docker", "label": "Postgres", "container": "pg"},
                    {
                        "id": "app",
                        "kind": "port",
                        "label": "App",
                        "port": 3000,
                        "url": "http://127.0.0.1:3000",
                    },
                ]
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["container"], "pg")
        self.assertEqual(targets[1]["port"], 3000)
        self.assertFalse(targets[0]["discovered"])

    def test_deferred_kinds(self):
        targets, _, _, errors = model.load_targets(
            {
                "targets": [
                    {"id": "svc", "kind": "systemd", "label": "Unit"},
                    {"id": "cmp", "kind": "compose", "dir": "/tmp"},
                    {"id": "proc", "kind": "process", "start": ["true"]},
                ]
            }
        )
        self.assertEqual(targets, [])
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("deferred" in e for e in errors))

    def test_duplicate_id(self):
        _, _, _, errors = model.load_targets(
            {
                "targets": [
                    {"id": "a", "kind": "port", "port": 1},
                    {"id": "a", "kind": "port", "port": 2},
                ]
            }
        )
        self.assertTrue(any("duplicate" in e for e in errors))


class MergeDiscoveryTests(unittest.TestCase):
    def test_empty_targets_plus_discovered(self):
        merged = model.merge_targets(
            [],
            [{"name": "pg", "id": "abc", "state": "running"}],
            [{"port": 3000, "comm": "node", "docker_backed": False, "localhost": True}],
        )
        ids = [t["id"] for t in merged]
        self.assertEqual(ids, ["port:3000", "docker:pg"])
        self.assertTrue(all(t["discovered"] for t in merged))
        self.assertEqual(merged[0]["url"], "http://127.0.0.1:3000")

    def test_ignore_filters(self):
        merged = model.merge_targets(
            [],
            [
                {"name": "pg", "state": "running"},
                {"name": "noise", "state": "exited"},
            ],
            [
                {"port": 3000, "comm": "node", "docker_backed": False},
                {"port": 53, "comm": "systemd-resolve", "docker_backed": False},
            ],
            ignore_docker={"noise"},
            ignore_ports={53},
        )
        ids = {t["id"] for t in merged}
        self.assertEqual(ids, {"docker:pg", "port:3000"})

    def test_pin_port_still_present(self):
        pinned, _, _, _ = model.load_targets(
            {
                "targets": [
                    {
                        "id": "app",
                        "kind": "port",
                        "label": "App",
                        "port": 3000,
                        "url": "http://127.0.0.1:3000/admin",
                    }
                ]
            }
        )
        merged = model.merge_targets(
            pinned,
            [],
            [{"port": 3000, "comm": "node", "docker_backed": False}],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "app")
        self.assertEqual(merged[0]["url"], "http://127.0.0.1:3000/admin")
        self.assertFalse(merged[0]["discovered"])

    def test_pin_docker_does_not_duplicate(self):
        pinned, _, _, _ = model.load_targets(
            {
                "targets": [
                    {"id": "db", "kind": "docker", "label": "Postgres", "container": "pg"}
                ]
            }
        )
        merged = model.merge_targets(
            pinned,
            [{"name": "pg", "state": "running"}, {"name": "redis", "state": "running"}],
            [],
        )
        ids = [t["id"] for t in merged]
        self.assertEqual(ids, ["db", "docker:redis"])
        self.assertEqual(merged[0]["label"], "Postgres")

    def test_docker_proxy_port_skipped(self):
        merged = model.merge_targets(
            [],
            [{"name": "web", "state": "running"}],
            [
                {
                    "port": 8080,
                    "comm": "docker-proxy",
                    "docker_backed": True,
                    "localhost": True,
                }
            ],
        )
        ids = [t["id"] for t in merged]
        self.assertEqual(ids, ["docker:web"])
        self.assertNotIn("port:8080", ids)


class ClassifyGroupTests(unittest.TestCase):
    def test_docker_is_container(self):
        self.assertEqual(model.classify_group(kind="docker"), "container")

    def test_pinned_port_is_localhost(self):
        self.assertEqual(
            model.classify_group(kind="port", port=631, discovered=False),
            "localhost",
        )

    def test_httpish_and_app_ports(self):
        self.assertEqual(
            model.classify_group(kind="port", port=3000, discovered=True),
            "localhost",
        )
        self.assertEqual(
            model.classify_group(kind="port", port=11434, comm="ollama", discovered=True),
            "localhost",
        )
        self.assertEqual(
            model.classify_group(kind="port", port=5173, comm="node", discovered=True),
            "localhost",
        )
        self.assertEqual(
            model.classify_group(kind="port", port=4640, comm="node-MainThread", discovered=True),
            "localhost",
        )

    def test_noise_ports(self):
        self.assertEqual(
            model.classify_group(kind="port", port=631, comm="cupsd", discovered=True),
            "port",
        )
        self.assertEqual(
            model.classify_group(kind="port", port=1883, comm="mosquitto", discovered=True),
            "port",
        )
        self.assertEqual(
            model.classify_group(
                kind="port", port=12345, comm="ssh-agent", discovered=True
            ),
            "port",
        )

    def test_comm_allowlist(self):
        self.assertEqual(
            model.classify_group(kind="port", port=45678, comm="vite", discovered=True),
            "localhost",
        )


class GroupSortFilterTests(unittest.TestCase):
    def _rows(self):
        targets = [
            {"id": "z", "kind": "docker", "label": "zebra", "container": "zebra", "discovered": True},
            {"id": "a", "kind": "docker", "label": "alpha", "container": "alpha", "discovered": True},
            {"id": "p3000", "kind": "port", "label": ":3000", "port": 3000, "discovered": True},
            {"id": "p631", "kind": "port", "label": ":631", "port": 631, "discovered": True},
            {"id": "p8080", "kind": "port", "label": ":8080", "port": 8080, "discovered": True},
        ]
        return model.build_status(
            targets,
            docker_reachable=True,
            docker_probes={
                "z": {"state": "stopped"},
                "a": {"state": "running"},
            },
            port_probes={
                "p3000": {"listening": True, "comm": "node"},
                "p631": {"listening": True, "comm": "cupsd"},
                "p8080": {"listening": False, "comm": "python"},
            },
            filters={"showContainers": True, "showLocalhosts": True, "showPorts": True},
        )

    def test_groups_and_sort(self):
        status = self._rows()
        g = status["groups"]
        self.assertEqual([r["id"] for r in g["containers"]], ["a", "z"])  # running then stopped
        self.assertEqual(g["containers"][0]["state"], "running")
        # Localhosts: up (3000) before down (8080); port ascending within state
        self.assertEqual([r["id"] for r in g["localhosts"]], ["p3000", "p8080"])
        self.assertEqual([r["id"] for r in g["ports"]], ["p631"])
        self.assertEqual(g["ports"][0]["group"], "port")
        self.assertEqual(g["localhosts"][0]["group"], "localhost")
        self.assertEqual(status["sortMode"], "default")

    def test_sort_mode_az_and_port(self):
        targets = [
            {"id": "z", "kind": "docker", "label": "zebra", "container": "zebra", "discovered": True},
            {"id": "a", "kind": "docker", "label": "alpha", "container": "alpha", "discovered": True},
            {"id": "p3000", "kind": "port", "label": ":3000", "port": 3000, "discovered": True},
            {"id": "p631", "kind": "port", "label": ":631", "port": 631, "discovered": True},
            {"id": "p8080", "kind": "port", "label": ":8080", "port": 8080, "discovered": True},
        ]
        probes = {
            "docker_reachable": True,
            "docker_probes": {"z": {"state": "stopped"}, "a": {"state": "running"}},
            "port_probes": {
                "p3000": {"listening": True, "comm": "node"},
                "p631": {"listening": True, "comm": "cupsd"},
                "p8080": {"listening": False, "comm": "python"},
            },
            "filters": {"showContainers": True, "showLocalhosts": True, "showPorts": True},
        }
        az = model.build_status(targets, sort_mode="az", **probes)
        self.assertEqual(az["sortMode"], "az")
        self.assertEqual([r["id"] for r in az["groups"]["containers"]], ["a", "z"])
        self.assertEqual([r["id"] for r in az["groups"]["localhosts"]], ["p3000", "p8080"])
        self.assertEqual([r["id"] for r in az["groups"]["ports"]], ["p631"])

        by_port = model.build_status(targets, sort_mode="port", **probes)
        self.assertEqual(by_port["sortMode"], "port")
        # Localhosts sorted by port number regardless of up/down
        self.assertEqual([r["id"] for r in by_port["groups"]["localhosts"]], ["p3000", "p8080"])
        self.assertEqual([r["id"] for r in by_port["groups"]["ports"]], ["p631"])

        # Stopped zebra before running alpha when sorting A–Z only by label —
        # already checked; force reverse labels via port mode on containers (all port 0 → label)
        self.assertEqual(
            model.normalize_sort_mode("A-Z"),
            "az",
        )
        self.assertEqual(model.normalize_sort_mode("nope"), "default")

    def test_default_filters_hide_ports_from_counts(self):
        status = model.build_status(
            [
                {"id": "db", "kind": "docker", "label": "db", "container": "db", "discovered": True},
                {"id": "cups", "kind": "port", "label": ":631", "port": 631, "discovered": True},
                {"id": "app", "kind": "port", "label": ":3000", "port": 3000, "discovered": True},
            ],
            docker_reachable=True,
            docker_probes={"db": {"state": "running"}},
            port_probes={
                "cups": {"listening": True, "comm": "cupsd"},
                "app": {"listening": True, "comm": "node"},
            },
            # default filters: Ports off
        )
        self.assertEqual(status["filters"]["showPorts"], False)
        self.assertEqual(status["counts"]["running"], 2)  # db + app; cups hidden
        self.assertEqual(status["counts"]["total"], 2)
        # groups still list cups for the panel when Ports is flipped on
        self.assertEqual(len(status["groups"]["ports"]), 1)

    def test_filter_rows_respects_toggles(self):
        status = self._rows()
        only_ports = model.filter_rows(
            status["targets"],
            {"showContainers": False, "showLocalhosts": False, "showPorts": True},
        )
        self.assertEqual([r["id"] for r in only_ports], ["p631"])

    def test_ignore_token(self):
        self.assertEqual(
            model.ignore_token_for({"kind": "docker", "meta": {"container": "pg"}}),
            "docker:pg",
        )
        self.assertEqual(
            model.ignore_token_for({"kind": "port", "meta": {"port": 3000}}),
            "port:3000",
        )


class BuildStatusTests(unittest.TestCase):
    def setUp(self):
        self.targets, _, _, _ = model.load_targets(
            {
                "targets": [
                    {"id": "db", "kind": "docker", "container": "pg"},
                    {"id": "web", "kind": "port", "port": 8080},
                ]
            }
        )

    def test_docker_unreachable_still_returns_status(self):
        status = model.build_status(
            self.targets,
            docker_reachable=False,
            port_probes={"web": {"listening": True, "comm": "python", "pid": 9}},
        )
        by_id = {t["id"]: t for t in status["targets"]}
        self.assertFalse(status["docker"]["reachable"])
        self.assertEqual(by_id["db"]["state"], "unknown")
        self.assertEqual(by_id["db"]["error"], "docker unavailable")
        self.assertEqual(by_id["db"]["actions"], [])
        self.assertEqual(by_id["web"]["state"], "running")
        # Pinned python listener with pid → Stop/Pause (no restart without can_restart).
        self.assertEqual(set(by_id["web"]["actions"]), {"pause", "stop"})
        self.assertFalse(by_id["web"]["statusOnly"])
        self.assertEqual(by_id["web"]["group"], "localhost")  # pinned
        # Bar counts the up localhost even when docker is down.
        self.assertEqual(status["counts"]["running"], 1)

    def test_empty_targets_discovered_status(self):
        merged = model.merge_targets(
            [],
            [{"name": "pg", "state": "running"}],
            [{"port": 3000, "comm": "node", "docker_backed": False}],
        )
        status = model.build_status(
            merged,
            docker_reachable=True,
            docker_probes={"docker:pg": {"state": "running"}},
            port_probes={"port:3000": {"listening": True, "comm": "node", "pid": 42, "can_restart": True}},
        )
        self.assertEqual(status["counts"]["running"], 2)
        self.assertEqual(status["counts"]["total"], 2)
        by_id = {t["id"]: t for t in status["targets"]}
        self.assertEqual(set(by_id["docker:pg"]["actions"]), {"pause", "stop", "restart"})
        self.assertEqual(set(by_id["port:3000"]["actions"]), {"pause", "stop", "restart"})
        self.assertFalse(by_id["port:3000"]["statusOnly"])
        self.assertEqual(by_id["port:3000"]["url"], "http://127.0.0.1:3000")
        self.assertEqual(by_id["port:3000"]["group"], "localhost")
        self.assertEqual(by_id["docker:pg"]["group"], "container")
        self.assertEqual(len(status["groups"]["containers"]), 1)
        self.assertEqual(len(status["groups"]["localhosts"]), 1)

    def test_docker_proxy_port_not_counted_twice(self):
        # Explicit pin of a docker-published port: status-only, not in bar digit.
        pinned, _, _, _ = model.load_targets(
            {"targets": [{"id": "pub", "kind": "port", "port": 8080}]}
        )
        status = model.build_status(
            pinned
            + model.discovered_docker_targets([{"name": "web", "state": "running"}]),
            docker_reachable=True,
            docker_probes={"docker:web": {"state": "running"}},
            port_probes={
                "pub": {
                    "listening": True,
                    "comm": "docker-proxy",
                    "docker_backed": True,
                }
            },
        )
        self.assertEqual(status["counts"]["running"], 1)  # container only
        by_id = {t["id"]: t for t in status["targets"]}
        self.assertTrue(by_id["pub"]["meta"].get("dockerBacked"))

    def test_docker_running_actions(self):
        status = model.build_status(
            self.targets,
            docker_reachable=True,
            docker_probes={"db": {"state": "running"}},
            port_probes={"web": {"listening": False}},
        )
        by_id = {t["id"]: t for t in status["targets"]}
        db = by_id["db"]
        self.assertEqual(db["state"], "running")
        self.assertEqual(set(db["actions"]), {"pause", "stop", "restart"})
        self.assertEqual(db["primary"], "pause")

    def test_docker_paused_and_stopped(self):
        paused = model.build_target_status(
            self.targets[0],
            docker_reachable=True,
            docker_probe={"state": "paused"},
        )
        self.assertEqual(paused["primary"], "resume")
        self.assertIn("stop", paused["actions"])
        stopped = model.build_target_status(
            self.targets[0],
            docker_reachable=True,
            docker_probe={"state": "stopped"},
        )
        self.assertEqual(stopped["primary"], "start")
        self.assertEqual(set(stopped["actions"]), {"start", "restart"})

    def test_port_with_pid_gets_stop_pause(self):
        row = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "pid": 42, "comm": "node"},
        )
        self.assertEqual(set(row["actions"]), {"pause", "stop"})
        self.assertEqual(row["primary"], "pause")
        self.assertFalse(row["statusOnly"])

    def test_port_with_can_restart_includes_restart(self):
        row = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "pid": 42, "comm": "node", "can_restart": True},
        )
        self.assertEqual(set(row["actions"]), {"pause", "stop", "restart"})

    def test_port_paused_gets_resume_stop(self):
        row = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "pid": 42, "comm": "python", "paused": True, "can_restart": True},
        )
        self.assertEqual(row["state"], "paused")
        self.assertEqual(set(row["actions"]), {"resume", "stop", "restart"})
        self.assertEqual(row["primary"], "resume")

    def test_docker_proxy_port_no_stop(self):
        row = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "pid": 9, "comm": "docker-proxy", "docker_backed": True},
        )
        self.assertEqual(row["actions"], [])
        self.assertTrue(row["statusOnly"])

    def test_denylisted_process_no_stop(self):
        row = model.build_target_status(
            {"id": "dns", "kind": "port", "label": ":53", "port": 53, "discovered": True},
            docker_reachable=True,
            port_probe={"listening": True, "pid": 100, "comm": "systemd-resolved"},
        )
        self.assertEqual(row["actions"], [])
        self.assertTrue(row["statusOnly"])
        self.assertFalse(
            model.is_process_controllable(comm="sshd", pid=7, docker_backed=False)
        )

    def test_port_without_pid_no_actions(self):
        row = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "comm": "node"},
        )
        self.assertEqual(row["actions"], [])
        self.assertTrue(row["statusOnly"])

    def test_action_allowed(self):
        row = model.build_target_status(
            self.targets[0],
            docker_reachable=True,
            docker_probe={"state": "running"},
        )
        self.assertTrue(model.action_allowed(row, "stop"))
        self.assertTrue(model.action_allowed(row, "pause"))
        self.assertFalse(model.action_allowed(row, "start"))
        host = model.build_target_status(
            self.targets[1],
            docker_reachable=True,
            port_probe={"listening": True, "pid": 42, "comm": "node"},
        )
        self.assertTrue(model.action_allowed(host, "stop"))
        self.assertFalse(model.action_allowed(host, "start"))
        self.assertFalse(model.action_allowed(host, "restart"))


class ProbeParseTests(unittest.TestCase):
    def test_list_listening_ports_localhost_and_docker_proxy(self):
        ss_out = (
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            'LISTEN 0 128 127.0.0.1:3000 0.0.0.0:* users:(("node",pid=1234,fd=18))\n'
            'LISTEN 0 128 0.0.0.0:8080 0.0.0.0:* users:(("docker-proxy",pid=9,fd=4))\n'
            'LISTEN 0 128 192.168.1.5:9090 0.0.0.0:* users:(("app",pid=7,fd=3))\n'
            'LISTEN 0 128 [::1]:5173 [::]:* users:(("node",pid=8,fd=1))\n'
        )

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[0], "ss")
            return 0, ss_out, ""

        result = probes.list_listening_ports(run=fake_run)
        self.assertTrue(result["ok"])
        by_port = {L["port"]: L for L in result["listeners"]}
        self.assertTrue(by_port[3000]["localhost"])
        self.assertEqual(by_port[3000]["comm"], "node")
        self.assertTrue(by_port[8080]["docker_backed"])
        self.assertTrue(by_port[8080]["localhost"])  # wildcard
        self.assertFalse(by_port[9090]["localhost"])  # LAN-only
        self.assertTrue(by_port[5173]["localhost"])

    def test_list_listening_ports_prefers_localhost_pid(self):
        """LAN bind first must not keep its PID when a localhost bind appears."""
        ss_out = (
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            'LISTEN 0 128 192.168.1.5:3000 0.0.0.0:* users:(("lan-app",pid=111,fd=3))\n'
            'LISTEN 0 128 127.0.0.1:3000 0.0.0.0:* users:(("node",pid=222,fd=18))\n'
        )

        def fake_run(argv, **kwargs):
            return 0, ss_out, ""

        result = probes.list_listening_ports(run=fake_run)
        by_port = {L["port"]: L for L in result["listeners"]}
        self.assertTrue(by_port[3000]["localhost"])
        self.assertEqual(by_port[3000]["addr"], "127.0.0.1:3000")
        self.assertEqual(by_port[3000]["comm"], "node")
        self.assertEqual(by_port[3000]["pid"], 222)

    def test_run_cmd_keeps_large_stdout(self):
        big = ("x" * 5000) + "\n"

        def fake_run(argv, **kwargs):
            raise AssertionError("not used")

        # Exercise _cap via run_cmd with a real echo of large data is heavy;
        # unit-test the helper bound used by discovery.
        self.assertGreater(probes.STDOUT_CAP, 4096)
        kept = probes._cap(big * 2, probes.STDOUT_CAP)
        self.assertGreater(len(kept), 4096)
        small_err = probes._cap(big, probes.STDERR_CAP)
        self.assertLessEqual(len(small_err), probes.STDERR_CAP)

    def test_list_docker_containers(self):
        lines = "\n".join(
            [
                json.dumps({"ID": "abc123456789", "Names": "pg", "State": "running"}),
                json.dumps({"ID": "def123456789", "Names": "/redis", "State": "paused"}),
                json.dumps({"ID": "ghi123456789", "Names": "old", "State": "exited"}),
            ]
        )

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[:3], ["docker", "ps", "-a"])
            return 0, lines, ""

        result = probes.list_docker_containers(run=fake_run)
        self.assertTrue(result["ok"])
        by_name = {c["name"]: c for c in result["containers"]}
        self.assertEqual(by_name["pg"]["state"], "running")
        self.assertEqual(by_name["redis"]["state"], "paused")
        self.assertEqual(by_name["old"]["state"], "stopped")

    def test_probe_port_listening(self):
        ss_out = (
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            'LISTEN 0 128 127.0.0.1:8080 0.0.0.0:* users:(("node",pid=1234,fd=18))\n'
        )

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[0], "ss")
            return 0, ss_out, ""

        result = probes.probe_port(8080, run=fake_run)
        self.assertTrue(result["listening"])
        self.assertEqual(result["comm"], "node")
        self.assertEqual(result["pid"], 1234)

    def test_probe_port_not_listening(self):
        def fake_run(argv, **kwargs):
            return 0, "State\nLISTEN 0 128 127.0.0.1:22 0.0.0.0:*\n", ""

        result = probes.probe_port(9999, run=fake_run)
        self.assertFalse(result["listening"])

    def test_docker_inspect_paused(self):
        def fake_run(argv, **kwargs):
            return 0, json.dumps({"Running": True, "Paused": True}), ""

        result = probes.probe_docker_container("pg", run=fake_run)
        self.assertEqual(result["state"], "paused")

    def test_docker_inspect_missing(self):
        def fake_run(argv, **kwargs):
            return 1, "", "Error: No such object: pg"

        result = probes.probe_docker_container("pg", run=fake_run)
        self.assertEqual(result["state"], "stopped")

    def test_docker_reachable_no_socket(self):
        with mock.patch.object(probes.Path, "exists", return_value=False):

            def fake_run(argv, **kwargs):
                return 1, "", "Cannot connect"

            self.assertFalse(probes.docker_reachable(run=fake_run))

    def test_append_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            probes.append_log(path, {"action": "start", "ok": True})
            line = path.read_text(encoding="utf-8").strip()
            rec = json.loads(line)
            self.assertTrue(rec["ok"])
            self.assertIn("ts", rec)


if __name__ == "__main__":
    unittest.main()
