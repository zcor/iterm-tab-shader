from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "codex_state_broker.py"
SPEC = importlib.util.spec_from_file_location("codex_state_broker", MODULE_PATH)
assert SPEC and SPEC.loader
broker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = broker
SPEC.loader.exec_module(broker)


def make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY,
            target TEXT NOT NULL,
            process_uuid TEXT,
            feedback_log_body TEXT
        )
        """
    )
    return connection


def body(model: str = "None", effort: str = "None") -> str:
    return (
        "session_loop{x}: Submission sub=Submission { id: x, "
        "op: ThreadSettings { thread_settings: ThreadSettingsOverrides { "
        f"approval_policy: None, model: {model}, effort: {effort}, summary: None "
        "} } }"
    )


class ParsingTests(unittest.TestCase):
    def test_process_uuid_pid(self) -> None:
        self.assertEqual(4821, broker.parse_pid("pid:4821:abc"))
        self.assertIsNone(broker.parse_pid("thread:4821"))

    def test_model_and_effort(self) -> None:
        parsed = broker.parse_settings(
            'model: Some("gpt-5.6-terra"), effort: Some(Some(XHigh))'
        )
        self.assertEqual("gpt-5.6-terra", parsed.model)
        self.assertEqual("xhigh", parsed.effort)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = make_connection()

    def tearDown(self) -> None:
        self.connection.close()

    def insert(self, row_id: int, pid: int, text: str) -> None:
        self.connection.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?)",
            (row_id, broker.TARGET, f"pid:{pid}:uuid", text),
        )

    def test_latest_settings_merges_separate_changes(self) -> None:
        self.insert(1, 99, body('Some("gpt-5.6-sol")'))
        self.insert(2, 99, body('Some("gpt-5.6-terra")'))
        self.insert(3, 99, body(effort="Some(Some(High))"))
        self.insert(4, 100, body('Some("gpt-5.6-luna")'))
        self.assertEqual(
            broker.Settings("gpt-5.6-terra", "high"),
            broker.latest_settings(self.connection, 99),
        )

    def test_incremental_events_ignore_prompt_lookalike(self) -> None:
        self.insert(5, 99, body('Some("gpt-5.6-terra")'))
        self.insert(
            6,
            99,
            "session_loop{x}: Submission op: UserInput { text: "
            + body('Some("gpt-5.6-luna")'),
        )
        newest, events = broker.events_after(self.connection, 4)
        self.assertEqual(6, newest)
        self.assertEqual([(5, 99, broker.Settings("gpt-5.6-terra", ""))], events)


class FileTests(unittest.TestCase):
    def test_atomic_state_file_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tab.state"
            broker.atomic_write(path, "gpt-5.6-terra|xhigh\n")
            self.assertEqual("gpt-5.6-terra|xhigh\n", path.read_text())
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_registration_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "target"
            target.write_text(str(os.getpid()))
            link = directory / "tab.pid"
            link.symlink_to(target)
            self.assertIsNone(broker.read_registration(link))

    def test_unregistered_state_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            stale = directory / "gone.state"
            stale.write_text("gpt-5.6-sol|high\n")
            broker.remove_unregistered_states(directory, {"live"})
            self.assertFalse(stale.exists())

    def test_runtime_directory_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "runtime"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(OSError):
                broker.prepare_runtime(link)


class BrokerIntegrationTests(unittest.TestCase):
    def test_registration_seed_update_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "logs.sqlite"
            writer = sqlite3.connect(database)
            writer.execute(
                """
                CREATE TABLE logs (
                    id INTEGER PRIMARY KEY,
                    target TEXT NOT NULL,
                    process_uuid TEXT,
                    feedback_log_body TEXT
                )
                """
            )
            pid = os.getpid()
            writer.execute(
                "INSERT INTO logs VALUES (?, ?, ?, ?)",
                (1, broker.TARGET, f"pid:{pid}:uuid", body('Some("gpt-5.6-sol")')),
            )
            writer.commit()

            runtime = root / "runtime"
            broker.prepare_runtime(runtime)
            registration = runtime / "registrations" / "tab.pid"
            registration.write_text(f"{pid}\n", encoding="ascii")
            service = broker.Broker(database, runtime, 0.1, 1.0)
            service.refresh_registrations()
            self.assertTrue(service.connect())
            state = runtime / "states" / "tab.state"
            self.assertEqual("gpt-5.6-sol|\n", state.read_text())

            writer.execute(
                "INSERT INTO logs VALUES (?, ?, ?, ?)",
                (2, broker.TARGET, f"pid:{pid}:uuid", body(effort="Some(Some(XHigh))")),
            )
            writer.commit()
            service.poll_events()
            self.assertEqual("gpt-5.6-sol|xhigh\n", state.read_text())

            registration.unlink()
            service.refresh_registrations()
            self.assertFalse(state.exists())
            assert service.connection is not None
            service.connection.close()
            writer.close()


if __name__ == "__main__":
    unittest.main()
