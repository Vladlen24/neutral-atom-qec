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
        width=max(x for x, y in positions) + 1,
        height=max(y for x, y in positions) + 1,
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
    test.assertTrue(all(len(path) == frames for path in paths))
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
                        a, b = positions[atom], positions[other]
                        test.assertGreaterEqual(
                            abs(a[0] - b[0]) + abs(a[1] - b[1]), config["r_crosstalk"]
                        )
        else:
            selected = set(event["gates"])
            for i, j in itertools.combinations(range(len(paths)), 2):
                a, b = positions[i], positions[j]
                distance = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if (i, j) in selected:
                    test.assertLessEqual(distance, config["r_int"])
                else:
                    test.assertGreaterEqual(distance, config["r_block"])
    test.assertEqual(
        sum(event["transport_steps"] for event in data["layers"]), data["total_steps"]
    )
    json.dumps(data)


class CandidateSelection(unittest.TestCase):
    def test_repeated_occurrences_and_global_order(self):
        gates = [
            (0, ("rx", 1)),
            (0, ("rz", 2)),
            (1, ("rx", 3)),
            ("global", ("ry", 4)),
            (1, ("rz", 5)),
        ]
        ops = index_gate_operations(gates, 2)
        self.assertEqual(get_layer_candidates(ops), [ops[0], ops[2]])
        self.assertEqual(get_layer_candidates(ops[3:]), ops[3:4])

    def test_exhaustive_partial_layers_preserve_atom_order(self):
        for size in range(6):
            for targets in itertools.product([0, 1, "global"], repeat=size):
                ops = index_gate_operations(
                    [(target, ("rx", index)) for index, target in enumerate(targets)], 2
                )
                pending, executed = list(ops), []
                while pending:
                    candidates = get_layer_candidates(pending)
                    selected = candidates[-1]
                    executed.append(selected)
                    pending = [op for op in pending if op[0] != selected[0]]
                self.assertEqual(
                    sorted(gid for gid, gate in executed), list(range(size))
                )
                for atom in range(2):
                    self.assertEqual(
                        [
                            gid
                            for gid, (target, rotation) in executed
                            if target in (atom, "global")
                        ],
                        [
                            gid
                            for gid, (target, rotation) in ops
                            if target in (atom, "global")
                        ],
                    )

    def test_invalid_inputs(self):
        for gate in [
            (0,),
            (-1, ("rx", 1)),
            (2, ("ry", 1)),
            (True, ("rx", 1)),
            (0, ("bad", 1)),
        ]:
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                index_gate_operations([gate], 2)


class ScheduleExamples(unittest.TestCase):
    def test_complete_default_program(self):
        data = compile_quiet(DEFAULT_GATES)
        assert_schedule(self, data, DEFAULT_GATES)
        self.assertEqual(len(data["layers"]), 6)
        self.assertEqual(data["total_steps"], 6)

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


if __name__ == "__main__":
    unittest.main()
