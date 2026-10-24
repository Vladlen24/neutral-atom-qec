"""Small SAT/UNSAT examples of the documented physical and discrete rules."""

import unittest

from z3 import Bool, BoolVal, IntVal, Not, Solver, is_true, sat, unsat

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


class TrapSupportExamples(unittest.TestCase):
    def test_atom_needs_an_slm_site_or_a_complete_aod_intersection(self):
        x, y = atom_coordinates([(1, 1)])
        for slm_sites, row_on, col_on, expected in [
            ([], False, False, unsat),
            ([(1, 1)], False, False, sat),
            ([], True, True, sat),
            ([], True, False, unsat),
        ]:
            with self.subTest(slm_sites=slm_sites, row_on=row_on, col_on=col_on):
                solver = Solver()
                constraints.add_trap_support(
                    solver,
                    x,
                    y,
                    line_states([(1, row_on)]),
                    line_states([(1, col_on)]),
                    slm_sites,
                )
                self.assertEqual(solver.check(), expected)

    def test_line_deactivation_requires_slm_even_if_another_line_supports_atom(self):
        x, y = atom_coordinates([(0, 0), (0, 0)])
        rows = line_states([(0, True), (0, True)], [(0, False), (0, True)])
        columns = line_states([(0, True)], [(0, True)])
        for slm_sites, expected in [([], unsat), ([(0, 0)], sat)]:
            solver = Solver()
            constraints.add_trap_support(solver, x, y, rows, columns, slm_sites)
            self.assertEqual(solver.check(), expected)


class PairSelectionExamples(unittest.TestCase):
    def test_overlapping_cz_pairs_cannot_share_a_layer(self):
        chosen = {(0, 1): Bool("choose_01"), (0, 2): Bool("choose_02")}
        solver = Solver()
        constraints.add_one_pair_per_atom(solver, chosen, 3)
        constraints.add_selected_pair_count(solver, chosen, 2)
        self.assertEqual(solver.check(), unsat)

    def test_lower_cardinality_can_choose_either_candidate(self):
        chosen = {(0, 1): Bool("choose_01"), (0, 2): Bool("choose_02")}
        for excluded, remaining in [((0, 1), (0, 2)), ((0, 2), (0, 1))]:
            with self.subTest(excluded=excluded):
                solver = Solver()
                constraints.add_one_pair_per_atom(solver, chosen, 3)
                constraints.add_selected_pair_count(solver, chosen, 1)
                solver.add(Not(chosen[excluded]))
                self.assertEqual(solver.check(), sat)
                self.assertTrue(is_true(solver.model().eval(chosen[remaining])))

    def test_unselected_candidate_is_subject_to_isolation(self):
        x, y = atom_coordinates([(0, 0)], [(1, 0)])
        for selected, expected in [(True, sat), (False, unsat)]:
            solver = Solver()
            chosen = {(0, 1): BoolVal(selected)}
            constraints.add_interaction_distance(solver, x, y, {(0, 1)}, 1, chosen)
            constraints.add_blockade_distance(solver, x, y, {(0, 1)}, 3, chosen)
            self.assertEqual(solver.check(), expected)


if __name__ == "__main__":
    unittest.main()
