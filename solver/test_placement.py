"""Behavioral checks for placement feasibility, scheduling, and failure handling."""

import unittest
from unittest.mock import patch

from z3 import unknown

from solver.placement import DEFAULT_GATES, compile_placement


def line_architecture(sites, starts=None, **radii):
    return {
        "width": max(sites) + 1,
        "height": 1,
        "slm_sites": [(x, 0) for x in sites],
        "starts": [(x, 0) for x in (sites if starts is None else starts)],
        "r_int": 1,
        "r_block": 3,
        "r_crosstalk": 2,
        **radii,
    }


class PlacementTests(unittest.TestCase):
    def assert_valid_schedule(self, gates, result, routed=False):
        config = result["architecture"]
        previous = config["starts"]
        sites = set(map(tuple, config["slm_sites"]))
        atom_count = len(previous)
        actual_order = [[] for _ in previous]
        expected_order = [[] for _ in previous]
        seen = []
        for operation_id, (target, payload) in enumerate(gates):
            targets = (
                range(atom_count)
                if target == "global"
                else (target, payload) if isinstance(payload, int) else (target,)
            )
            for atom in targets:
                expected_order[atom].append(operation_id)
        for layer in result["layers"]:
            positions = list(map(tuple, layer["positions"]))
            self.assertEqual(len(positions), atom_count)
            self.assertEqual(len(set(positions)), atom_count)
            self.assertTrue(set(positions) <= sites)
            touched, pairs, targets = [], set(), set()
            for op in layer["operations"]:
                seen.append(op["id"])
                self.assertEqual(op["type"], layer["type"])
                for atom in op["targets"]:
                    actual_order[atom].append(op["id"])
                    touched.append(atom)
                if layer["type"] == "rydberg":
                    pairs.add(tuple(sorted(op["targets"])))
                targets.update(op["targets"])
            self.assertEqual(len(touched), len(set(touched)))
            for i, (x, y) in enumerate(positions):
                for j in range(i):
                    d = abs(x - positions[j][0]) + abs(y - positions[j][1])
                    if layer["type"] == "rydberg":
                        if (j, i) in pairs:
                            self.assertLessEqual(d, config["r_int"])
                        else:
                            self.assertGreaterEqual(d, config["r_block"])
                    elif layer["type"] == "local" and ({i, j} & targets):
                        self.assertGreaterEqual(d, config["r_crosstalk"])
            if layer["type"] == "global":
                self.assertEqual(positions, list(map(tuple, previous)))
                self.assertEqual(len(layer["operations"]), 1)
            previous = positions
        self.assertEqual(sorted(seen), list(range(len(gates))))
        self.assertEqual(actual_order, expected_order)
        self.assertEqual(result["routing_verified"], routed)

    def test_ten_atom_example(self):
        result = compile_placement(DEFAULT_GATES, timeout_ms=10000)
        self.assert_valid_schedule(DEFAULT_GATES, result)
        self.assertEqual(
            [len(layer["operations"]) for layer in result["layers"]], [1, 3, 3, 3, 3, 1]
        )

    def test_surface_code_distance_three(self):
        from solver.surface_code_d3 import ARCHITECTURE, ATOM_ROLES, build_gate_seq

        gates = build_gate_seq()
        result = compile_placement(gates, architecture=ARCHITECTURE, timeout_ms=10000)
        self.assert_valid_schedule(gates, result)
        self.assertEqual(len(gates), 76)
        self.assertEqual(ATOM_ROLES.count("data"), 9)
        self.assertEqual(ATOM_ROLES.count("ancilla"), 8)
        cz_layers = [layer for layer in result["layers"] if layer["type"] == "rydberg"]
        self.assertEqual(len(cz_layers), 4)
        self.assertEqual(sum(len(layer["operations"]) for layer in cz_layers), 24)

    def test_mixed_repeated_operations_and_consecutive_global_rotations(self):
        gates = [
            (0, ("rx", 0.5)),
            (1, ("rz", 0.2)),
            (0, 1),
            (0, ("rx", -0.5)),
            (0, 1),
            ("global", ("ry", 0.3)),
            ("global", ("ry", -0.3)),
            (2, ("rz", 0.2)),
            (2, 3),
        ]
        result = compile_placement(
            gates, architecture=line_architecture([0, 1, 4, 5, 8, 9], [0, 1, 4, 5])
        )
        self.assert_valid_schedule(gates, result)
        self.assertEqual(result["layers"][0]["type"], "local")
        self.assertEqual(len(result["layers"][0]["operations"]), 2)

    def test_cz_cardinality_fallback_and_spectator_isolation(self):
        gates = [(0, 1), (2, 3)]
        result = compile_placement(gates, architecture=line_architecture([0, 1, 4, 8]))
        self.assert_valid_schedule(gates, result)
        self.assertEqual(
            [len(layer["operations"]) for layer in result["layers"]], [1, 1]
        )
        self.assertEqual(
            [(c["K"], c["result"]) for c in result["checks"]],
            [(2, "unsat"), (1, "sat"), (1, "sat")],
        )

    def test_local_cardinality_fallback_allows_close_spectators(self):
        gates = [(0, ("rx", 0.5)), (1, ("rz", 0.5))]
        result = compile_placement(gates, architecture=line_architecture([0, 1, 4]))
        self.assert_valid_schedule(gates, result)
        self.assertEqual(
            [len(layer["operations"]) for layer in result["layers"]], [1, 1]
        )

    def test_global_and_empty_program_need_no_solver(self):
        for gates in ([], [("global", ("ry", 0.5))]):
            result = compile_placement(gates, architecture=line_architecture([0, 1]))
            self.assert_valid_schedule(gates, result)
            self.assertEqual(result["checks"], [])

    def test_global_still_requires_valid_slm_occupancy(self):
        for starts in ([0, 0], [0, 2]):
            with self.subTest(starts=starts), self.assertRaises(ValueError):
                compile_placement(
                    [("global", ("ry", 0.5))],
                    architecture=line_architecture([0, 1], starts),
                )

    def test_unplaceable_layer_stops(self):
        with self.assertRaisesRegex(ValueError, "No feasible rydberg"):
            compile_placement([(0, 1)], architecture=line_architecture([0, 4]))
        # A ready CZ cannot bypass a geometrically infeasible ready local gate.
        with self.assertRaisesRegex(ValueError, "No feasible local"):
            compile_placement(
                [(0, ("rx", 0.5)), (1, 2)],
                architecture=line_architecture([0, 1, 2], r_crosstalk=4),
            )

    def test_unknown_does_not_reduce_cardinality(self):
        with patch("solver.placement.Solver.check", return_value=unknown) as check:
            with patch(
                "solver.placement.Solver.reason_unknown", return_value="test timeout"
            ):
                with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
                    compile_placement(
                        [(0, 1), (2, 3)], architecture=line_architecture([0, 1, 4, 8])
                    )
        self.assertEqual(check.call_count, 1)


if __name__ == "__main__":
    unittest.main()
