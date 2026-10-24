"""Small SAT/UNSAT examples of the documented physical and discrete rules."""

import unittest

from z3 import BoolVal, IntVal, Solver, sat, unsat

from solver import constraints


def atom_coordinates(*paths):
    return (
        [[IntVal(x) for x, _ in path] for path in paths],
        [[IntVal(y) for _, y in path] for path in paths],
    )


def line_states(*steps):
    return [
        [(IntVal(position), BoolVal(enabled)) for position, enabled in step]
        for step in steps
    ]


class ConstraintExamples(unittest.TestCase):
    def test_grid_boundary(self):
        for position, expected in [((4, 4), sat), ((5, 4), unsat), ((-1, 0), unsat)]:
            with self.subTest(position=position):
                solver = Solver()
                x, y = atom_coordinates([position])
                constraints.add_atom_bounds(solver, x, y, 5, 5)
                self.assertEqual(solver.check(), expected)

    def test_coincident_atoms_are_forbidden(self):
        solver = Solver()
        x, y = atom_coordinates([(1, 1)], [(1, 1)])
        constraints.add_vertex_conflicts(solver, x, y)
        self.assertEqual(solver.check(), unsat)

    def test_swap_is_forbidden_even_without_vertex_collision(self):
        x, y = atom_coordinates([(0, 0), (1, 0)], [(1, 0), (0, 0)])
        solver = Solver()
        constraints.add_vertex_conflicts(solver, x, y)
        self.assertEqual(solver.check(), sat)
        constraints.add_swap_conflicts(solver, x, y)
        self.assertEqual(solver.check(), unsat)

    def test_captured_atom_follows_its_intersection(self):
        rows = line_states([(0, True)], [(1, True)])
        columns = line_states([(0, True)], [(0, True)])
        for destination, expected in [((0, 1), sat), ((1, 1), unsat)]:
            with self.subTest(destination=destination):
                x, y = atom_coordinates([(0, 0), destination])
                solver = Solver()
                constraints.add_captured_atom_motion(solver, x, y, rows, columns)
                self.assertEqual(solver.check(), expected)

    def test_uncaptured_atom_cannot_move(self):
        rows = line_states([(0, False)], [(0, False)])
        columns = line_states([(0, False)], [(0, False)])
        for destination, expected in [((0, 0), sat), ((1, 0), unsat)]:
            x, y = atom_coordinates([(0, 0), destination])
            solver = Solver()
            constraints.add_uncaptured_atom_wait(solver, x, y, rows, columns)
            self.assertEqual(solver.check(), expected)

    def test_any_switch_blocks_continuous_line_motion(self):
        rows = line_states([(0, True), (2, False)], [(1, True), (2, True)])
        columns = line_states([(0, True)], [(0, True)])
        solver = Solver()
        constraints.add_no_motion_during_switch(solver, rows, columns)
        self.assertEqual(solver.check(), unsat)

    def test_speed_limit_applies_to_continuously_active_lines(self):
        for initially_enabled, expected in [(True, unsat), (False, sat)]:
            rows = line_states([(0, initially_enabled)], [(2, True)])
            columns = line_states([], [])
            solver = Solver()
            constraints.add_line_speed_limit(solver, rows, columns)
            self.assertEqual(solver.check(), expected)

    def test_active_line_order_cannot_reverse(self):
        rows = line_states([(0, True), (1, True)], [(1, True), (0, True)])
        solver = Solver()
        constraints.add_line_order(solver, rows, line_states([], []))
        self.assertEqual(solver.check(), unsat)

    def test_order_rule_does_not_add_distinctness_on_activation(self):
        rows = line_states([(0, False), (0, False)], [(1, True), (1, True)])
        solver = Solver()
        constraints.add_line_order(solver, rows, line_states([], []))
        self.assertEqual(solver.check(), sat)

    def test_cz_quality_and_spectator_isolation(self):
        for partner, spectator, expected in [
            ((1, 0), (4, 4), sat),
            ((2, 0), (4, 4), unsat),
            ((1, 0), (1, 1), unsat),
        ]:
            with self.subTest(partner=partner, spectator=spectator):
                x, y = atom_coordinates([(0, 0)], [partner], [spectator])
                solver = Solver()
                constraints.add_interaction_distance(solver, x, y, {(0, 1)}, 1)
                constraints.add_blockade_distance(solver, x, y, {(0, 1)}, 3)
                self.assertEqual(solver.check(), expected)


if __name__ == "__main__":
    unittest.main()
