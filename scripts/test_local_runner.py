"""Process ownership checks use mocks; no servers or network connections."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_runner import Runner


class RunnerTests(unittest.TestCase):
    def test_no_pid_file_or_reused_pid_never_signals_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(Path(directory))
            with patch("local_runner.os.killpg") as signal_group:
                runner.stop()
                runner.run_dir.mkdir()
                record = {"pid": 12345, "root": str(runner.root), "stamp": "old-start"}
                (runner.run_dir / "backend.json").write_text(json.dumps(record))
                with (
                    patch("local_runner.os.getpgid", return_value=12345),
                    patch("local_runner.process_stamp", return_value="new-start"),
                ):
                    runner.stop_one("backend")
                signal_group.assert_not_called()

    def test_foreign_root_and_non_session_leader_are_not_owned(self):
        runner = Runner(Path("/tmp/talent-insight-runner-test"))
        self.assertFalse(
            runner.owns({"pid": 1, "root": str(runner.root), "stamp": "same"})
        )
        self.assertFalse(
            runner.owns({"pid": 12345, "root": "/another-project", "stamp": "same"})
        )
        with patch("local_runner.os.getpgid", return_value=23456):
            self.assertFalse(
                runner.owns({"pid": 12345, "root": str(runner.root), "stamp": "same"})
            )

    def test_conflicting_port_blocks_start_without_launching(self):
        runner = Runner(Path("/tmp/talent-insight-runner-test"))
        with (
            patch("local_runner.sys.version_info", (3, 12)),
            patch.dict(os.environ, {"CONDA_DEFAULT_ENV": "talent-insight"}),
            patch("local_runner.subprocess.run") as run,
            patch("local_runner.importlib.util.find_spec", return_value=object()),
            patch.object(Path, "is_file", return_value=True),
            patch("local_runner.port_available", return_value=False),
            patch("local_runner.subprocess.Popen") as launch,
        ):
            run.return_value.stdout = "v24.13.0"
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                runner.start()
            launch.assert_not_called()

    def test_rejects_invalid_or_duplicate_ports(self):
        for port in ("0", "65536", "3000", "bad"):
            with (
                patch.dict(os.environ, {"BACKEND_PORT": port, "FRONTEND_PORT": "3000"}),
                self.assertRaises(ValueError),
            ):
                Runner(Path("/tmp"))


if __name__ == "__main__":
    unittest.main()
