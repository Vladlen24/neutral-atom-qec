"""SMT constraints for discrete neutral-atom transport and gate scheduling.

See README.md for the constraint definitions and model assumptions.
"""

from z3 import Abs, And, Implies, Not, Or, PbEq, PbLe


def add_atom_bounds(s, atom_x, atom_y, W, H):
    """Keep every atom inside the W by H grid at every step."""
    for xs, ys in zip(atom_x, atom_y):
        for x, y in zip(xs, ys):
            s.add(x >= 0, x < W, y >= 0, y < H)


def add_active_line_bounds(s, r, c, W, H):
    """Keep active AOD line coordinates inside the grid."""
    for rows, cols in zip(r, c):
        for y, on in rows:
            s.add(Implies(on, And(y >= 0, y < H)))
        for x, on in cols:
            s.add(Implies(on, And(x >= 0, x < W)))


def add_initial_lines_off(s, r, c):
    """Disable every AOD row and column at t=0."""
    for _, on in r[0] + c[0]:
        s.add(Not(on))


def add_initial_line_state(s, r, c, initial_rows, initial_cols):
    """Set the initial AOD line state; coordinates of inactive lines remain unconstrained."""
    for lines, initial in ((r, initial_rows), (c, initial_cols)):
        for (position, on), (initial_position, initial_on) in zip(lines[0], initial):
            s.add(on == initial_on)
            if initial_on:
                s.add(position == initial_position)


def add_initial_atom_positions(s, atom_x, atom_y, starts):
    """Fix initial atom coordinates from starts."""
    for i, (x, y) in enumerate(starts):
        s.add(atom_x[i][0] == x, atom_y[i][0] == y)


def add_line_speed_limit(s, r, c):
    """Limit a continuously active AOD line to one grid unit of displacement per step."""
    for lines in (r, c):
        for before, after in zip(lines, lines[1:]):
            for (pos, on), (next_pos, next_on) in zip(before, after):
                s.add(Implies(And(on, next_on), Abs(next_pos - pos) <= 1))


def add_line_order(s, r, c):
    """Preserve the strict order of two AOD lines while both remain continuously active."""
    for lines in (r, c):
        for before, after in zip(lines, lines[1:]):
            for i in range(len(before)):
                for j in range(i + 1, len(before)):
                    both_on = And(before[i][1], before[j][1], after[i][1], after[j][1])
                    s.add(
                        Implies(
                            And(both_on, before[i][0] < before[j][0]),
                            after[i][0] < after[j][0],
                        )
                    )
                    s.add(
                        Implies(
                            And(both_on, before[i][0] > before[j][0]),
                            after[i][0] > after[j][0],
                        )
                    )


def _switching(r, c, t):
    """Return the SMT condition for any AOD line switching between t and t+1."""
    return Or(
        *[
            before[1] != after[1]
            for lines in (r, c)
            for before, after in zip(lines[t], lines[t + 1])
        ]
    )


def add_no_motion_during_switch(s, r, c):
    """Forbid motion of continuously active lines while any AOD line switches."""
    for t in range(len(r) - 1):
        row_motion = Or(
            *[
                And(before[1], after[1], before[0] != after[0])
                for before, after in zip(r[t], r[t + 1])
            ]
        )
        col_motion = Or(
            *[
                And(before[1], after[1], before[0] != after[0])
                for before, after in zip(c[t], c[t + 1])
            ]
        )
        s.add(Implies(_switching(r, c, t), And(Not(row_motion), Not(col_motion))))


def add_captured_atom_motion(s, atom_x, atom_y, r, c):
    """Move a captured atom with its AOD intersection when no line switches."""
    for t in range(len(r) - 1):
        switching = _switching(r, c, t)
        for i in range(len(atom_x)):
            for j, (row_y, row_on) in enumerate(r[t]):
                for k, (col_x, col_on) in enumerate(c[t]):
                    captured = And(
                        row_on, col_on, atom_y[i][t] == row_y, atom_x[i][t] == col_x
                    )
                    s.add(
                        Implies(
                            And(Not(switching), captured),
                            And(
                                atom_y[i][t + 1] == r[t + 1][j][0],
                                atom_x[i][t + 1] == c[t + 1][k][0],
                            ),
                        )
                    )


def add_uncaptured_atom_wait(s, atom_x, atom_y, r, c):
    """Keep an atom stationary during switching or without a capturing AOD intersection."""
    for t in range(len(r) - 1):
        switching = _switching(r, c, t)
        for i in range(len(atom_x)):
            captured_by = [
                And(row_on, col_on, atom_y[i][t] == row_y, atom_x[i][t] == col_x)
                for row_y, row_on in r[t]
                for col_x, col_on in c[t]
            ]
            s.add(
                Implies(
                    Or(switching, Not(Or(*captured_by))),
                    And(
                        atom_x[i][t + 1] == atom_x[i][t],
                        atom_y[i][t + 1] == atom_y[i][t],
                    ),
                )
            )


def add_trap_support(s, atom_x, atom_y, r, c, slm_sites):
    """Require SLM or active AOD support; deactivate a line passing through an atom only at an SLM site."""
    T = len(r) - 1
    for t in range(T + 1):
        for i in range(len(atom_x)):
            on_island = Or(
                *[And(atom_x[i][t] == x, atom_y[i][t] == y) for x, y in slm_sites]
            )
            on_active_row = Or(*[And(on, atom_y[i][t] == y) for y, on in r[t]])
            on_active_col = Or(*[And(on, atom_x[i][t] == x) for x, on in c[t]])
            s.add(Or(on_island, And(on_active_row, on_active_col)))
            if t < T:
                for j, (y, on) in enumerate(r[t]):
                    s.add(
                        Implies(
                            And(on, Not(r[t + 1][j][1]), atom_y[i][t] == y), on_island
                        )
                    )
                for j, (x, on) in enumerate(c[t]):
                    s.add(
                        Implies(
                            And(on, Not(c[t + 1][j][1]), atom_x[i][t] == x), on_island
                        )
                    )


def add_vertex_conflicts(s, atom_x, atom_y):
    """Forbid two atoms from occupying the same site at the same step."""
    for t in range(len(atom_x[0])):
        for i in range(len(atom_x)):
            for j in range(i + 1, len(atom_x)):
                s.add(Or(atom_x[i][t] != atom_x[j][t], atom_y[i][t] != atom_y[j][t]))


def _final_distance(atom_x, atom_y, i, j):
    """Return the Manhattan distance between atoms i and j at the final step."""
    return Abs(atom_x[i][-1] - atom_x[j][-1]) + Abs(atom_y[i][-1] - atom_y[j][-1])


def local_gate_isolation(atom_x, atom_y, targets, r_crosstalk):
    """Return final-state isolation predicates for operation IDs mapped to addressed atoms."""
    return {
        operation_id: And(
            *[
                _final_distance(atom_x, atom_y, target, other) >= r_crosstalk
                for other in range(len(atom_x))
                if other != target
            ]
        )
        for operation_id, target in targets.items()
    }


def add_interaction_distance(s, atom_x, atom_y, cz_set, r_int, chosen=None):
    """Bring selected CZ pairs within r_int; without selection, constrain every required pair."""
    for i in range(len(atom_x)):
        for j in range(i + 1, len(atom_x)):
            if (i, j) in cz_set:
                close = _final_distance(atom_x, atom_y, i, j) <= r_int
                s.add(close if chosen is None else Implies(chosen[i, j], close))


def add_blockade_distance(s, atom_x, atom_y, cz_set, r_block, chosen=None):
    """Keep unselected and noncandidate pairs at least r_block apart at the final step."""
    for i in range(len(atom_x)):
        for j in range(i + 1, len(atom_x)):
            pair = (i, j)
            far = _final_distance(atom_x, atom_y, i, j) >= r_block
            if pair not in cz_set:
                s.add(far)
            elif chosen is not None:
                s.add(Implies(Not(chosen[pair]), far))


def add_selected_pair_count(s, chosen, count):
    """Select exactly count CZ pairs for the current Rydberg layer."""
    s.add(PbEq([(selected, 1) for selected in chosen.values()], count))


def add_one_pair_per_atom(s, chosen, atom_count):
    """Allow at most one selected CZ pair per atom in a layer."""
    for atom in range(atom_count):
        incident = [selected for pair, selected in chosen.items() if atom in pair]
        if len(incident) > 1:
            s.add(PbLe([(selected, 1) for selected in incident], 1))


def add_swap_conflicts(s, atom_x, atom_y):
    """Forbid two atoms from exchanging sites in one step."""
    for t in range(len(atom_x[0]) - 1):
        for i in range(len(atom_x)):
            for j in range(i + 1, len(atom_x)):
                s.add(
                    Not(
                        And(
                            atom_x[i][t] == atom_x[j][t + 1],
                            atom_y[i][t] == atom_y[j][t + 1],
                            atom_x[j][t] == atom_x[i][t + 1],
                            atom_y[j][t] == atom_y[i][t + 1],
                        )
                    )
                )
