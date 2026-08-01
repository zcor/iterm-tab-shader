from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "iterm_attention.py"
SPEC = importlib.util.spec_from_file_location("iterm_attention", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
attention = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = attention
SPEC.loader.exec_module(attention)


class AttentionHelpersTest(unittest.TestCase):
    def test_claude_attention_marker(self) -> None:
        self.assertTrue(attention.needs_attention(" ✳ waiting"))
        self.assertFalse(attention.needs_attention("waiting"))

    def test_codex_completion(self) -> None:
        self.assertTrue(attention.codex_just_finished("⣾ work (codex)", "work (codex)"))
        self.assertFalse(attention.codex_just_finished("work (codex)", "work (codex)"))
        self.assertFalse(attention.codex_just_finished("⣾ work", "work"))

    def test_note_scale_wraps_and_rises(self) -> None:
        self.assertEqual(("do4", 1.0), attention.note_for_position(1))
        self.assertEqual(("sol4", 1.5), attention.note_for_position(5))
        self.assertEqual(("do5", 2.0), attention.note_for_position(6))
        self.assertEqual(("do4", 1.0), attention.note_for_position(0))


if __name__ == "__main__":
    unittest.main()
