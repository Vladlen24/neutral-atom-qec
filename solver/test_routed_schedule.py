"""Routing feedback, complete example replay, and gate-only snapshot semantics."""

import unittest
from unittest.mock import patch

from solver import placement
from solver.routing import route_transition, validate_route
from solver.surface_code_d3 import ARCHITECTURE, build_gate_seq
from solver import test_placement


class RoutedScheduleTests(unittest.TestCase):
    def check_schedule(self, gates, schedule):
        test_placement.PlacementTests().assert_valid_schedule(
            gates, schedule, routed=True
        )
        current = schedule["architecture"]["starts"]
        for layer in schedule["layers"]:
            self.assertTrue(
                validate_route(
                    current,
                    layer["positions"],
                    layer["route"],
                    schedule["architecture"],
                )
            )
            current = layer["positions"]
        frames = placement.routing_frames(schedule)
        sites = set(map(tuple, schedule["architecture"]["slm_sites"]))
        for before, after in zip(frames, frames[1:]):
            changed = [
                i
                for i, (a, b) in enumerate(zip(before["positions"], after["positions"]))
                if a != b
            ]
            self.assertLessEqual(len(changed), 1)
            if after["type"] == "transport":
                self.assertEqual(len(set(after["positions"])), len(after["positions"]))
                self.assertLessEqual(
                    sum(tuple(p) not in sites for p in after["positions"]), 1
                )
                if after["aod"] is not None:
                    self.assertEqual(
                        after["positions"][after["moving_atom"]], after["aod"]
                    )

    def test_steane_and_surface(self):
        for gates, config in [
            (placement.DEFAULT_GATES, placement.DEFAULT_ARCHITECTURE),
            (build_gate_seq(), ARCHITECTURE),
        ]:
            with self.subTest(atoms=len(config["starts"])):
                schedule = placement.compile_placement(
                    gates, architecture=config, routing=True, timeout_ms=15000
                )
                self.check_schedule(gates, schedule)

    def test_failure_reduces_k_and_discards_trial_moves(self):
        config = {
            "width": 9,
            "height": 4,
            "slm_sites": [(x, y) for y in (0, 3) for x in (0, 1, 4, 5, 8)],
            "starts": [(0, 0), (4, 0), (0, 3), (4, 3)],
        }
        gates = [(0, 1), (2, 3), ("global", ("ry", 0.5)), (0, 1)]
        calls = []

        def trial(starts, goals, architecture):
            calls.append(list(starts))
            route = route_transition(starts, goals, architecture)
            self.assertTrue(route["success"])
            if len(calls) == 1:
                self.assertTrue(route["moves"])
                route["success"], route["reason"] = (
                    False,
                    "test_rejection_after_partial_plan",
                )
            return route

        with patch("solver.placement.route_transition", side_effect=trial):
            schedule = placement.compile_placement(
                gates, architecture=config, routing=True
            )
        self.check_schedule(gates, schedule)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(
            [(c["layer"], c["K"]) for c in schedule["checks"][:2]], [(0, 2), (0, 1)]
        )
        self.assertEqual([len(l["operations"]) for l in schedule["layers"][:2]], [1, 1])
        self.assertFalse(schedule["checks"][0]["routing"]["success"])

    def test_k_one_failure_stops_without_executing(self):
        with patch(
            "solver.placement.route_transition",
            return_value={"success": False, "reason": "no_parking_site"},
        ) as router:
            with self.assertRaisesRegex(ValueError, "placement and route.*K=1"):
                placement.compile_placement([(0, 1)], routing=True)
        self.assertEqual(router.call_count, 1)
