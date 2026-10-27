"""Validate gate highlighting without requiring ffmpeg or writing videos."""

import contextlib
import io
import unittest
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle

from solver import visualization


def capture_frames(events=None, pulses=None):
    frames = []

    class CaptureAnimation:
        def __init__(self, fig, update, frames, **options):
            self.fig, self.update, self.count = fig, update, frames

        def save(self, destination, writer):
            for index in range(self.count):
                self.update(index)
                ax = self.fig.axes[0]
                overlays = {
                    color: [
                        (
                            tuple(p.get_xy()),
                            p.get_width(),
                            p.get_height(),
                            p.get_alpha(),
                        )
                        for p in ax.patches
                        if isinstance(p, Rectangle)
                        and p.get_fill()
                        and p.get_visible()
                        and p.get_facecolor()[:3] == to_rgb(color)
                    ]
                    for color in ["blue", "green", "orange"]
                }
                frames.append((ax.get_title(), overlays))

    with patch.object(visualization, "FuncAnimation", CaptureAnimation), patch.object(
        visualization.writers, "is_available", return_value=True
    ), patch.object(visualization, "FFMpegWriter"), contextlib.redirect_stdout(
        io.StringIO()
    ):
        visualization.animate_atom_paths(
            [[0] * 5 for _ in range(3)],
            [[(0, 0), (1, 0)], [(3, 0), (3, 1)]],
            marked_cells=[(0, 0), (3, 0)],
            gate_layers=events,
            rydberg_layers=pulses,
        )
    return frames


class GateHighlights(unittest.TestCase):
    def test_gate_events_sharing_a_transport_step_remain_separate(self):
        frames = capture_frames(
            [
                {"layer": 1, "step": 1, "type": "local", "gates": [(0, ("rx", 1))]},
                {
                    "layer": 2,
                    "step": 1,
                    "type": "global",
                    "gates": [("global", ("ry", 2))],
                },
                {
                    "layer": 3,
                    "step": 1,
                    "type": "global",
                    "gates": [("global", ("ry", 3))],
                },
            ]
        )
        self.assertEqual(len(frames), 5)
        self.assertEqual(frames[2][1]["blue"], [((0.5, -0.5), 1, 1, 0.25)])
        for index, layer in [(3, 2), (4, 3)]:
            self.assertEqual(frames[index][1]["green"], [((-0.5, -0.5), 5, 3, 0.25)])
            self.assertFalse(frames[index][1]["blue"])
            self.assertIn(f"layer {layer}", frames[index][0])

    def test_local_cells_follow_the_addressed_atoms_and_clear_during_transport(self):
        frames = capture_frames(
            [
                {
                    "layer": 1,
                    "step": 0,
                    "type": "local",
                    "gates": [(0, ("rx", 1)), (1, ("rz", 2))],
                },
                {
                    "layer": 2,
                    "step": 1,
                    "type": "local",
                    "gates": [(0, ("rx", 3)), (1, ("rz", 4))],
                },
            ]
        )
        self.assertEqual(
            frames[1][1]["blue"],
            [((-0.5, -0.5), 1, 1, 0.25), ((2.5, -0.5), 1, 1, 0.25)],
        )
        self.assertFalse(frames[2][1]["blue"])
        self.assertEqual(
            frames[3][1]["blue"], [((0.5, -0.5), 1, 1, 0.25), ((2.5, 0.5), 1, 1, 0.25)]
        )

    def test_cz_events_and_legacy_pulse_steps_use_orange(self):
        legacy = capture_frames(pulses=[(1, [(0, 1)])])
        self.assertEqual(len(legacy), 2)
        self.assertTrue(legacy[1][1]["orange"])
        frames = capture_frames(
            [
                {"layer": 1, "step": 1, "type": "rydberg", "gates": [(0, 1)]},
                {
                    "layer": 2,
                    "step": 1,
                    "type": "global",
                    "gates": [("global", ("ry", 1))],
                },
            ]
        )
        self.assertTrue(frames[2][1]["orange"])
        self.assertIn("2q layer 1", frames[2][0])
        self.assertFalse(frames[3][1]["orange"])
        self.assertTrue(frames[3][1]["green"])


if __name__ == "__main__":
    unittest.main()
