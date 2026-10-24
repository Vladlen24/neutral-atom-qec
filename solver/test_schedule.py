"""Validate a complete computed schedule using ordinary Python predicates."""

import contextlib
import io
import itertools
import unittest

from solver.compiler import main


class ScheduleExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.schedule = main()

    def test_boundaries_and_gate_coverage(self):
        data = self.schedule
        frame_count = data["total_steps"] + 1
        self.assertTrue(all(len(path) == frame_count for path in data["paths"]))
        self.assertEqual(len(data["rows"]), frame_count)
        self.assertEqual(len(data["columns"]), frame_count)
        self.assertEqual(
            [path[0] for path in data["paths"]],
            [(0, 0), (0, 1), (0, 2), (0, 3), (2, 0)],
        )
        self.assertEqual(data["rows"][0], [])
        self.assertEqual(data["columns"][0], [])
        expected = {(0, 1), (0, 2), (0, 3), (0, 4)}
        actual = [tuple(sorted(pair)) for _, pairs in data["layers"] for pair in pairs]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(len(data["layers"]), 4)
        pulse_steps = [step for step, _ in data["layers"]]
        self.assertEqual(pulse_steps, sorted(set(pulse_steps)))
        self.assertEqual(pulse_steps[-1], data["total_steps"])

    def test_states_and_transitions(self):
        data = self.schedule
        slm_sites = {(0, 0), (0, 1), (0, 2), (0, 3), (2, 0), (1, 1), (3, 2), (4, 4)}
        paths = data["paths"]
        for t in range(data["total_steps"] + 1):
            positions = [tuple(path[t]) for path in paths]
            self.assertEqual(len(set(positions)), len(positions))
            self.assertLessEqual(len(data["rows"][t]), 4)
            self.assertLessEqual(len(data["columns"][t]), 4)
            for x, y in positions:
                self.assertTrue(0 <= x < 5 and 0 <= y < 5)
                self.assertTrue(
                    (x, y) in slm_sites
                    or (y in data["rows"][t] and x in data["columns"][t])
                )
            if t:
                for path in paths:
                    before, after = path[t - 1], path[t]
                    self.assertLessEqual(abs(after[0] - before[0]), 1)
                    self.assertLessEqual(abs(after[1] - before[1]), 1)
                for first, second in itertools.combinations(paths, 2):
                    self.assertFalse(
                        first[t - 1] == second[t] and second[t - 1] == first[t]
                    )

    def test_global_pulse_quality_and_isolation(self):
        for step, selected in self.schedule["layers"]:
            selected = {tuple(sorted(pair)) for pair in selected}
            participants = [atom for pair in selected for atom in pair]
            self.assertEqual(len(participants), len(set(participants)))
            positions = [path[step] for path in self.schedule["paths"]]
            for i, j in itertools.combinations(range(len(positions)), 2):
                x_i, y_i = positions[i]
                x_j, y_j = positions[j]
                distance = abs(x_i - x_j) + abs(y_i - y_j)
                if (i, j) in selected:
                    self.assertLessEqual(distance, 1)
                else:
                    self.assertGreaterEqual(distance, 3)


if __name__ == "__main__":
    unittest.main()
