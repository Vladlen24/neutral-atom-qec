"""Check gate coverage, operation order, and physical schedule invariants."""

import contextlib
import io
import itertools
import json
import unittest
from solver.compiler import (
    DEFAULT_GATES,
    compile_schedule,
    get_layer_candidates,
    index_gate_operations,
)


def compile_quiet(gates, **options):
    with contextlib.redirect_stdout(io.StringIO()):
        return compile_schedule(gates, **options)


def static_architecture(positions, **options):
    return dict(
        width=max((x for x, y in positions)) + 1,
        height=max((y for x, y in positions)) + 1,
        starts=positions,
        slm_sites=positions,
        rows=0,
        columns=0,
        **options
    )


def assert_schedule(test, data, gates):
    config = data["architecture"]
    paths = data["paths"]
    frames = data["total_steps"] + 1
    test.assertTrue(all((len(path) == frames for path in paths)))
    test.assertEqual(len(data["rows"]), frames)
    test.assertEqual(len(data["columns"]), frames)
    test.assertEqual([p[0] for p in paths], config["starts"])
    completed = [gid for event in data["layers"] for gid in event["operation_ids"]]
    test.assertEqual(sorted(completed), list(range(len(gates))))

    def atoms(gate):
        target, payload = gate
        if isinstance(payload, int):
            return set(gate)
        return set(range(len(paths))) if target == "global" else {target}

    for atom in range(len(paths)):
        test.assertEqual(
            [gid for gid in completed if atom in atoms(gates[gid])],
            [gid for gid, gate in enumerate(gates) if atom in atoms(gate)],
        )
    for t in range(frames):
        positions = [p[t] for p in paths]
        test.assertEqual(len(set(positions)), len(positions))
        for x, y in positions:
            test.assertTrue(0 <= x < config["width"] and 0 <= y < config["height"])
            test.assertTrue(
                (x, y) in config["slm_sites"]
                or (y in data["rows"][t] and x in data["columns"][t])
            )
        if t:
            for path in paths:
                test.assertLessEqual(abs(path[t][0] - path[t - 1][0]), 1)
                test.assertLessEqual(abs(path[t][1] - path[t - 1][1]), 1)
            for first, second in itertools.combinations(paths, 2):
                test.assertFalse(
                    first[t - 1] == second[t] and second[t - 1] == first[t]
                )
    for event in data["layers"]:
        step = event["step"]
        positions = [p[step] for p in paths]
        for gid, gate in zip(event["operation_ids"], event["gates"]):
            expected = gates[gid]
            if isinstance(expected[1], int):
                expected = tuple(sorted(expected))
            test.assertEqual(gate, expected)
        if event["type"] == "global":
            test.assertEqual(len(event["gates"]), 1)
            test.assertEqual(event["transport_steps"], 0)
        elif event["type"] == "local":
            targets = [gate[0] for gate in event["gates"]]
            test.assertEqual(len(set(targets)), len(targets))
            for atom in targets:
                for other in range(len(paths)):
                    if atom != other:
                        a, b = (positions[atom], positions[other])
                        test.assertGreaterEqual(
                            abs(a[0] - b[0]) + abs(a[1] - b[1]), config["r_crosstalk"]
                        )
        else:
            selected = set(event["gates"])
            for i, j in itertools.combinations(range(len(paths)), 2):
                a, b = (positions[i], positions[j])
                distance = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if (i, j) in selected:
                    test.assertLessEqual(distance, config["r_int"])
                else:
                    test.assertGreaterEqual(distance, config["r_block"])
    test.assertEqual(
        sum((event["transport_steps"] for event in data["layers"])), data["total_steps"]
    )
    json.dumps(data)


class CandidateSelection(unittest.TestCase):

    def test_independent_local_gate_can_pass_an_earlier_cz(self):
        ops = index_gate_operations([(0, 1), (2, ("rx", 1)), (0, ("rz", 2))], 3)
        self.assertEqual(get_layer_candidates(ops), ("local", [ops[1]]))
        self.assertEqual(get_layer_candidates([ops[0], ops[2]]), ("rydberg", [ops[0]]))

    def test_skipped_cz_still_blocks_successors(self):
        ops = index_gate_operations([(0, 1), (0, 2), (2, ("rx", 1)), (3, ("rz", 2))], 4)
        self.assertEqual(get_layer_candidates(ops), ("local", [ops[3]]))
        self.assertEqual(get_layer_candidates(ops[:3]), ("rydberg", [ops[0]]))

    def test_repeated_occurrences_keep_original_ids(self):
        ops = index_gate_operations(
            [(1, 0), (0, ("rx", 1)), (0, 1), ("global", ("ry", 2)), (1, 0)], 2
        )
        self.assertEqual([op["id"] for op in ops], list(range(5)))
        self.assertEqual(
            [op["gate"] for op in ops if op["type"] == "rydberg"], [(0, 1)] * 3
        )

    def test_exhaustive_mixed_frontiers_and_partial_layers(self):
        choices = [
            (0, ("rx", 1)),
            (1, ("ry", 2)),
            (2, ("rz", 3)),
            (0, 1),
            (1, 2),
            (0, 2),
            ("global", ("ry", 4)),
        ]
        for size in range(5):
            for circuit in itertools.product(choices, repeat=size):
                original = index_gate_operations(circuit, 3)
                pending, executed = (list(original), [])
                while pending:
                    kind, candidates = get_layer_candidates(pending)
                    ready = [
                        op
                        for index, op in enumerate(pending)
                        if not any(
                            (
                                set(op["targets"]) & set(previous["targets"])
                                for previous in pending[:index]
                            )
                        )
                    ]
                    expected_kind = (
                        "local"
                        if any((op["type"] == "local" for op in ready))
                        else ready[0]["type"]
                    )
                    self.assertEqual(
                        (kind, candidates),
                        (
                            expected_kind,
                            [op for op in ready if op["type"] == expected_kind],
                        ),
                    )
                    selected = candidates[-1]
                    executed.append(selected)
                    pending = [op for op in pending if op["id"] != selected["id"]]
                for atom in range(3):
                    self.assertEqual(
                        [op["id"] for op in executed if atom in op["targets"]],
                        [op["id"] for op in original if atom in op["targets"]],
                    )

    def test_invalid_inputs(self):
        for gate in [
            (0,),
            (0, 0),
            (0, 3),
            (-1, 1),
            (True, 1),
            ("other", ("rx", 1)),
            (0, ("bad", 1)),
        ]:
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                index_gate_operations([gate], 3)


class ScheduleExamples(unittest.TestCase):

    def test_complete_default_program(self):
        data = compile_quiet(DEFAULT_GATES)
        assert_schedule(self, data, DEFAULT_GATES)
        self.assertEqual(
            [event["type"] for event in data["layers"]],
            ["local", "rydberg", "local", "global", "rydberg", "local", "global"],
        )
        self.assertTrue(
            all(
                (
                    2 <= event["transport_steps"] <= 10
                    for event in data["layers"]
                    if event["type"] != "global"
                )
            )
        )

    def test_global_only_and_empty_programs(self):
        for gates in [[], [("global", ("ry", 1)), ("global", ("ry", 1))]]:
            with self.subTest(gates=gates):
                data = compile_quiet(gates)
                assert_schedule(self, data, gates)
                self.assertEqual(data["total_steps"], 0)
                self.assertEqual(len(data["layers"]), len(gates))

    def test_crosstalk_ignores_spectator_to_spectator_distance(self):
        gates = [(1, ("rx", 1)), (0, ("rz", 2))]
        config = static_architecture([(0, 0), (3, 0), (3, 1)])
        with self.assertRaises(RuntimeError):
            compile_quiet(
                gates, architecture=config, layer_settings={"local": {"max_steps": 2}}
            )
        data = compile_quiet(gates[1:], architecture=config)
        assert_schedule(self, data, gates[1:])
        disabled = compile_quiet(
            gates, architecture=config, use_constraints={"crosstalk_distance": False}
        )
        self.assertEqual(len(disabled["layers"][0]["gates"]), 2)

    def test_parallelism_has_priority_over_transport_horizon(self):
        positions = [(0, 0), (3, 0), (3, 1)]
        config = dict(
            width=4, height=3, starts=positions, slm_sites=positions, rows=1, columns=1
        )
        gates = [(0, ("rx", 1)), (1, ("rz", 2))]
        settings = {"local": {"min_steps": 0, "max_steps": 2}}
        data = compile_quiet(gates, architecture=config, layer_settings=settings)
        assert_schedule(self, data, gates)
        self.assertEqual(
            (len(data["layers"][0]["gates"]), data["layers"][0]["transport_steps"]),
            (2, 2),
        )
        smaller = compile_quiet(gates[:1], architecture=config, layer_settings=settings)
        self.assertEqual(smaller["total_steps"], 0)

    def test_initial_support_is_validated_even_for_global(self):
        with self.assertRaises(ValueError):
            compile_quiet([("global", ("ry", 1))], architecture={"slm_sites": []})


class MixedPrograms(unittest.TestCase):

    def test_priority_and_layer_specific_constraints(self):
        gates = [(1, 2), (0, ("rx", 1))]
        data = compile_quiet(
            gates, architecture=static_architecture([(0, 0), (3, 0), (3, 1)])
        )
        assert_schedule(self, data, gates)
        self.assertEqual([e["type"] for e in data["layers"]], ["local", "rydberg"])
        self.assertEqual([e["operation_ids"] for e in data["layers"]], [[1], [0]])

    def test_repeated_cz_with_global_rotation(self):
        gates = [(0, 1), (1, 0), ("global", ("ry", 1)), (0, 1)]
        data = compile_quiet(gates, architecture=static_architecture([(0, 0), (1, 0)]))
        assert_schedule(self, data, gates)
        self.assertEqual(
            [e["type"] for e in data["layers"]],
            ["rydberg", "rydberg", "global", "rydberg"],
        )

    def test_strict_local_priority_stops_even_if_ready_cz_would_fit(self):
        config = static_architecture([(0, 0), (3, 0), (7, 0), (8, 0)], r_crosstalk=4)
        settings = {"local": {"max_steps": 2}, "rydberg": {"max_steps": 2}}
        with self.assertRaisesRegex(RuntimeError, "Automatic fallback"):
            compile_quiet(
                [(0, ("rx", 1)), (2, 3)], architecture=config, layer_settings=settings
            )
        data = compile_quiet([(2, 3)], architecture=config, layer_settings=settings)
        assert_schedule(self, data, [(2, 3)])

    def test_cz_cardinality_fallback_can_keep_either_candidate(self):
        for positions, expected in [
            ([(0, 0), (1, 0), (0, 4), (4, 4)], 0),
            ([(0, 0), (4, 0), (0, 4), (1, 4)], 1),
        ]:
            with self.subTest(expected=expected):
                import solver.compiler as compiler
                from unittest.mock import patch

                original = compiler.get_layer_candidates
                pending = []

                def record(operations):
                    pending.append([op["id"] for op in operations])
                    return original(operations)

                with patch.object(
                    compiler, "get_layer_candidates", record
                ), self.assertRaises(RuntimeError):
                    compile_quiet(
                        [(0, 1), (2, 3)],
                        architecture=static_architecture(positions),
                        layer_settings={"rydberg": {"max_steps": 2}},
                    )
                self.assertEqual(pending[0], [0, 1])
                self.assertEqual(pending[1], [1 - expected])

    def test_only_cz_layers_create_selection_variables(self):
        import solver.compiler as compiler
        from unittest.mock import patch

        original = compiler.Bool
        names = []

        def record(name):
            names.append(name)
            return original(name)

        with patch.object(compiler, "Bool", record):
            compile_quiet(
                [(1, 2), (0, ("rx", 1))],
                architecture=static_architecture([(0, 0), (3, 0), (3, 1)]),
            )
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith("_chosen"))

    def test_unknown_is_not_treated_as_unsat(self):
        import solver.compiler as compiler
        from unittest.mock import patch

        checks = []

        class LimitedSolver(compiler.Solver):

            def check(self):
                checks.append(1)
                return super().check() if len(checks) == 1 else compiler.unknown

            def reason_unknown(self):
                return "test resource limit"

        with patch.object(compiler, "Solver", LimitedSolver), self.assertRaisesRegex(
            RuntimeError, "UNKNOWN"
        ):
            compile_quiet(
                [(0, ("rx", 1))], architecture=static_architecture([(0, 0), (3, 0)])
            )
        self.assertEqual(len(checks), 2)


if __name__ == "__main__":
    unittest.main()
