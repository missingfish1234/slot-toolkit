"""Sidebar wheel scrolling must not reach numeric Spinbox class actions."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_diamond_alignment_editor import _AlignmentEditor


class SidebarWheelTests(unittest.TestCase):
    def test_wheel_scrolls_sidebar_and_stops_the_spinbox_class_action(self):
        editor = _AlignmentEditor.__new__(_AlignmentEditor)
        editor.side_canvas = SimpleNamespace(yview_scroll=Mock())
        numeric_value = 12.0
        # Tk's widget binding runs before its TSpinbox class binding. Only
        # "break" prevents that class from generating Increment/Decrement.
        for delta in (120, -120, 240, -240, 30):
            with self.subTest(delta=delta):
                event = SimpleNamespace(delta=delta)
                result = editor.scroll_sidebar(event)
                if result != 'break':
                    numeric_value += 1 if delta > 0 else -1
                self.assertEqual(numeric_value, 12.0)
                self.assertEqual(result, 'break')
                editor.side_canvas.yview_scroll.assert_called_with(-int(delta / 120), 'units')


if __name__ == '__main__':
    unittest.main(verbosity=2)
