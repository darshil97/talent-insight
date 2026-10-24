"""Local process management only: no install, certificates, migrations or seeding."""

import argparse
import errno
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

SERVICES = ("backend", "frontend")


def process_stamp(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def port_available(port: int) -> bool:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                return False
            raise


class Runner:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.run_dir = self.root / ".run_local"
        self.ports = {
            "backend": int(os.environ.get("BACKEND_PORT", "8000")),
            "frontend": int(os.environ.get("FRONTEND_PORT", "3000")),
        }
        if len(set(self.ports.values())) != 2 or any(
            not 1 <= port <= 65535 for port in self.ports.values()
        ):
            raise ValueError(
                "Use distinct BACKEND_PORT and FRONTEND_PORT values from 1 to 65535."
            )

    def record(self, service: str) -> dict:
        try:
            value = json.loads((self.run_dir / f"{service}.json").read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def owns(self, record: dict) -> bool:
        pid = record.get("pid")
        if type(pid) is not int or pid <= 1 or record.get("root") != str(self.root):
            return False
        try:
            return (
                os.getpgid(pid) == pid
                and bool(record.get("stamp"))
                and process_stamp(pid) == record["stamp"]
            )
        except ProcessLookupError:
            return False

    def preflight(self) -> None:
        if (
            sys.version_info[:2] != (3, 12)
            or os.environ.get("CONDA_DEFAULT_ENV") != "talent-insight"
        ):
            raise RuntimeError(
                "Use the existing talent-insight Conda environment (Python 3.12)."
            )
        runtime = Path(sys.executable).parent
        node = subprocess.run(
            [str(runtime / "node"), "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        if not node.stdout.startswith("v24."):
            raise RuntimeError("The talent-insight environment must provide Node 24.")
        if (
            importlib.util.find_spec("uvicorn") is None
            or importlib.util.find_spec("app") is None
        ):
            raise RuntimeError(
                "Install the locked backend dependencies following docs/local-development.md."
            )
        if not (self.root / "frontend/node_modules/next/dist/bin/next").is_file():
            raise RuntimeError(
                "Run npm ci in frontend with Conda active before starting."
            )
        for service, port in self.ports.items():
            record = self.record(service)
            if self.owns(record):
                if record.get("port") != port:
                    raise RuntimeError(
                        "Stop the managed servers before changing ports."
                    )
            elif not port_available(port):
                raise RuntimeError(
                    f"Port {port} is already occupied. Its process was left untouched."
                )

    def start(self) -> None:
        self.preflight()
        self.run_dir.mkdir(mode=0o700, exist_ok=True)
        self.run_dir.chmod(0o700)
        env = os.environ.copy()
        env.setdefault("NEXT_TELEMETRY_DISABLED", "1")
        env.setdefault(
            "NEXT_PUBLIC_API_BASE_URL", f"http://127.0.0.1:{self.ports['backend']}"
        )
        env.setdefault(
            "CORS_ALLOWED_ORIGINS",
            json.dumps(
                [
                    f"http://127.0.0.1:{self.ports['frontend']}",
                    f"http://localhost:{self.ports['frontend']}",
                ]
            ),
        )
        commands = {
            "backend": [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.ports["backend"]),
                "--no-access-log",
            ],
            "frontend": [
                str(Path(sys.executable).parent / "npm"),
                "run",
                "dev",
                "--",
                "--port",
                str(self.ports["frontend"]),
            ],
        }
        started = []
        try:
            for service in SERVICES:
                if self.owns(self.record(service)):
                    print(f"{service}: already running")
                    continue
                log_path = self.run_dir / f"{service}.log"
                log_path.touch(mode=0o600, exist_ok=True)
                log_path.chmod(0o600)
                with log_path.open("a") as log:
                    process = subprocess.Popen(
                        commands[service],
                        cwd=self.root / service,
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                record = {
                    "pid": process.pid,
                    "stamp": process_stamp(process.pid),
                    "root": str(self.root),
                    "port": self.ports[service],
                }
                record_path = self.run_dir / f"{service}.json"
                record_path.write_text(json.dumps(record))
                record_path.chmod(0o600)
                started.append(service)
                path = "/health" if service == "backend" else "/"
                deadline = time.monotonic() + 30
                ready = False
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{self.ports[service]}{path}", timeout=1
                        ) as response:
                            ready = response.status == 200
                        if ready:
                            break
                    except (URLError, TimeoutError):
                        pass
                    time.sleep(0.1)
                if not ready:
                    raise RuntimeError(
                        f"{service} did not become ready. See .run_local/{service}.log."
                    )
                print(f"{service}: started (pid {process.pid})")
        except (Exception, KeyboardInterrupt):
            for service in reversed(started):
                self.stop_one(service)
            raise
        self.status()

    def stop_one(self, service: str) -> None:
        record = self.record(service)
        if self.owns(record):
            pid = record["pid"]
            # Each managed server has its own session. Signal its reloader/npm
            # children as well, without touching an unrelated listener by port.
            try:
                os.killpg(pid, signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        os.killpg(pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.1)
                else:
                    os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            print(f"{service}: stopped")
        else:
            print(f"{service}: no owned live process; other processes left untouched")
        (self.run_dir / f"{service}.json").unlink(missing_ok=True)

    def stop(self) -> None:
        for service in reversed(SERVICES):
            self.stop_one(service)

    def status(self) -> None:
        for service in SERVICES:
            record = self.record(service)
            if self.owns(record):
                print(
                    f"{service}: running (pid {record['pid']}) http://127.0.0.1:{record['port']}"
                )
            elif port_available(self.ports[service]):
                print(f"{service}: stopped")
            else:
                print(
                    f"{service}: port {self.ports[service]} occupied by an unmanaged process"
                )

    def logs(self) -> None:
        paths = [self.run_dir / f"{service}.log" for service in SERVICES]
        if not all(path.is_file() for path in paths):
            raise RuntimeError("No logs yet. Start the servers first.")
        subprocess.run(["tail", "-n", "50", "-f", *map(str, paths)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["start", "stop", "status", "restart", "logs"]
    )
    args = parser.parse_args()
    try:
        runner = Runner(Path(__file__).resolve().parents[1])
        if args.command == "restart":
            runner.stop()
            runner.start()
        else:
            getattr(runner, args.command)()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Local runner: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
