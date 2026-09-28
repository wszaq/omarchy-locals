#!/usr/bin/env python3
"""Fixture tests for per-row resource KPIs (docker stats + /proc samples)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import model, probes  # noqa: E402


class HumanizeTests(unittest.TestCase):
    def test_humanize_bytes(self):
        self.assertEqual(probes.humanize_bytes(None), "—")
        self.assertEqual(probes.humanize_bytes(42), "42B")
        self.assertEqual(probes.humanize_bytes(512 * 1024), "512K")
        self.assertEqual(probes.humanize_bytes(128 * 1024 * 1024), "128M")
        self.assertEqual(probes.humanize_bytes(int(1.5 * 1024 * 1024 * 1024)), "1.5G")

    def test_format_cpu_percent(self):
        self.assertEqual(probes.format_cpu_percent(None), "—")
        self.assertEqual(probes.format_cpu_percent(0.0), "0%")
        self.assertEqual(probes.format_cpu_percent(0.12), "0.1%")
        self.assertEqual(probes.format_cpu_percent(12.4), "12%")


class DockerStatsParseTests(unittest.TestCase):
    def test_parse_docker_size(self):
        self.assertEqual(probes.parse_docker_size("45.2MiB"), int(round(45.2 * 1024**2)))
        self.assertEqual(probes.parse_docker_size("1.23kB"), 1230)
        self.assertEqual(probes.parse_docker_size("890B"), 890)
        self.assertIsNone(probes.parse_docker_size(""))
        self.assertIsNone(probes.parse_docker_size(None))

    def test_parse_mem_usage(self):
        self.assertEqual(
            probes.parse_docker_mem_usage("45.2MiB / 7.765GiB"),
            int(round(45.2 * 1024**2)),
        )

    def test_resources_from_docker_stats(self):
        obj = {
            "Name": "pg",
            "CPUPerc": "12.50%",
            "MemUsage": "128MiB / 8GiB",
            "MemPerc": "1.56%",
            "NetIO": "1.2kB / 0B",
            "BlockIO": "0B / 0B",
            "PIDs": "7",
        }
        res = probes.resources_from_docker_stats(obj)
        self.assertEqual(res["cpu"], "12%")
        self.assertEqual(res["mem"], "128M")
        self.assertEqual(res["memBytes"], 128 * 1024 * 1024)
        self.assertEqual(res["third"], "7")
        self.assertEqual(res["thirdLabel"], "PIDs")

    def test_list_docker_stats_batch(self):
        lines = "\n".join(
            [
                json.dumps(
                    {
                        "Name": "pg",
                        "CPUPerc": "0.10%",
                        "MemUsage": "64MiB / 8GiB",
                        "PIDs": "3",
                    }
                ),
                json.dumps(
                    {
                        "Name": "/redis",
                        "CPUPerc": "1.00%",
                        "MemUsage": "32MiB / 8GiB",
                        "PIDs": "1",
                    }
                ),
            ]
        )

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[:3], ["docker", "stats", "--no-stream"])
            self.assertIn("{{json .}}", argv)
            return 0, lines, ""

        result = probes.list_docker_stats(run=fake_run)
        self.assertTrue(result["ok"])
        self.assertEqual(result["by_name"]["pg"]["third"], "3")
        self.assertEqual(result["by_name"]["redis"]["cpu"], "1.0%")
        self.assertEqual(result["by_name"]["redis"]["mem"], "32M")

    def test_list_docker_stats_failure(self):
        def fake_run(argv, **kwargs):
            return 1, "", "permission denied"

        result = probes.list_docker_stats(run=fake_run)
        self.assertFalse(result["ok"])
        self.assertEqual(result["by_name"], {})


class ProcSampleTests(unittest.TestCase):
    def test_cpu_percent_from_delta(self):
        # 50 jiffies over 1.0s at 100 Hz → 50% of one core.
        pct = probes.cpu_percent_from_delta(
            prev_jiffies=100,
            prev_ts=10.0,
            cur_jiffies=150,
            cur_ts=11.0,
            clk_tck=100,
        )
        self.assertAlmostEqual(pct, 50.0, places=3)

    def test_cpu_percent_first_sample(self):
        self.assertIsNone(
            probes.cpu_percent_from_delta(
                prev_jiffies=None,
                prev_ts=None,
                cur_jiffies=10,
                cur_ts=1.0,
                clk_tck=100,
            )
        )

    def test_sample_pid_resources_with_fixtures(self):
        # Drive sample_pid_resources through mocked /proc readers.
        with (
            mock.patch.object(
                probes, "read_proc_stat_cpu", side_effect=[(200, 4), (250, 4)]
            ),
            mock.patch.object(probes, "read_proc_rss_bytes", return_value=64 * 1024 * 1024),
            mock.patch.object(probes, "read_proc_threads", return_value=4),
        ):
            res1, entry1 = probes.sample_pid_resources(
                42,
                prev=None,
                now=100.0,
                clk_tck=100,
            )
            self.assertEqual(res1["cpu"], "—")  # first sample
            self.assertEqual(res1["mem"], "64M")
            self.assertEqual(res1["third"], "4")
            self.assertEqual(entry1["jiffies"], 200)

            res2, entry2 = probes.sample_pid_resources(
                42,
                prev=entry1,
                now=101.0,
                clk_tck=100,
            )
            # +50 jiffies / 1s / 100Hz = 50%
            self.assertEqual(res2["cpu"], "50%")
            self.assertEqual(entry2["jiffies"], 250)

    def test_sample_pids_resources_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cpu-sample.json"
            with (
                mock.patch.object(probes, "read_proc_stat_cpu", return_value=(100, 2)),
                mock.patch.object(probes, "read_proc_rss_bytes", return_value=1024),
                mock.patch.object(probes, "read_proc_threads", return_value=2),
            ):
                out1 = probes.sample_pids_resources(
                    [555], sample_path=path, now=1.0, clk_tck=100
                )
                self.assertEqual(out1[555]["cpu"], "—")
                store = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(store["pids"]["555"]["jiffies"], 100)

            with (
                mock.patch.object(probes, "read_proc_stat_cpu", return_value=(150, 2)),
                mock.patch.object(probes, "read_proc_rss_bytes", return_value=2048),
                mock.patch.object(probes, "read_proc_threads", return_value=2),
            ):
                out2 = probes.sample_pids_resources(
                    [555], sample_path=path, now=2.0, clk_tck=100
                )
                self.assertEqual(out2[555]["cpu"], "50%")
                self.assertEqual(out2[555]["mem"], "2K")


class ModelResourcesAttachTests(unittest.TestCase):
    def test_docker_row_keeps_resources(self):
        row = model.build_target_status(
            {"id": "docker:pg", "kind": "docker", "label": "pg", "container": "pg"},
            docker_reachable=True,
            docker_probe={
                "state": "running",
                "error": None,
                "resources": {
                    "cpu": "1.0%",
                    "mem": "32M",
                    "memBytes": 32 * 1024 * 1024,
                    "third": "3",
                    "thirdLabel": "PIDs",
                },
            },
        )
        self.assertEqual(row["resources"]["cpu"], "1.0%")
        self.assertEqual(row["resources"]["third"], "3")
        self.assertTrue(row["hasResourceKpis"])
        self.assertEqual(row["kpiMem"], "32M")

    def test_port_row_keeps_resources(self):
        row = model.build_target_status(
            {
                "id": "port:3000",
                "kind": "port",
                "label": ":3000",
                "port": 3000,
                "discovered": True,
            },
            docker_reachable=False,
            port_probe={
                "listening": True,
                "comm": "node",
                "pid": 1234,
                "docker_backed": False,
                "paused": False,
                "can_restart": True,
                "error": None,
                "resources": {
                    "cpu": "2.5%",
                    "mem": "128M",
                    "memBytes": 128 * 1024 * 1024,
                    "third": "11",
                    "thirdLabel": "PIDs",
                },
            },
        )
        self.assertEqual(row["group"], "localhost")
        self.assertEqual(row["resources"]["mem"], "128M")

    def test_no_resources_when_absent(self):
        row = model.build_target_status(
            {"id": "docker:pg", "kind": "docker", "label": "pg", "container": "pg"},
            docker_reachable=True,
            docker_probe={"state": "running", "error": None},
        )
        self.assertNotIn("resources", row)


if __name__ == "__main__":
    unittest.main()
