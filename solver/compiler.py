"""Extract reusable SMT constraint functions.

Reconstructed research stage; see README.md for formulas and assumptions.
"""

import argparse
from pathlib import Path
import time
from z3 import Bool, Int, Solver, is_true, sat

if __package__:
    from .constraints import (
        add_active_line_bounds,
        add_atom_bounds,
        add_blockade_distance,
        add_captured_atom_motion,
        add_initial_atom_positions,
        add_initial_lines_off,
        add_interaction_distance,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_swap_conflicts,
        add_uncaptured_atom_wait,
        add_vertex_conflicts,
    )
else:
    from constraints import (
        add_active_line_bounds,
        add_atom_bounds,
        add_blockade_distance,
        add_captured_atom_motion,
        add_initial_atom_positions,
        add_initial_lines_off,
        add_interaction_distance,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_swap_conflicts,
        add_uncaptured_atom_wait,
        add_vertex_conflicts,
    )


def main(animate=False, output_dir=None):
    """Solve the original example; edit the architecture and program parameters below."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent / "output"
    if animate:
        if __package__:
            from .visualization import animate_atom_paths, plot_atom_paths
        else:
            from visualization import animate_atom_paths, plot_atom_paths
    MIN_STEPS = 5
    MAX_STEPS = 10
    W, H = (5, 5)
    r_int = 1
    r_block = 3
    start = time.time()
    starts = [(0, 0), (0, 1), (0, 2), (0, 3), (2, 0)]
    cz_pairs = [(0, 2), (1, 3)]
    cz_set = {tuple(sorted(pair)) for pair in cz_pairs}
    N = len(starts)
    r_max = 4
    c_max = 4
    use_constraints = {
        "atom_bounds": True,
        "active_line_bounds": True,
        "initial_lines_off": True,
        "initial_atom_positions": True,
        "line_speed_limit": True,
        "line_order": True,
        "no_motion_during_switch": True,
        "captured_atom_motion": True,
        "uncaptured_atom_wait": True,
        "vertex_conflicts": True,
        "interaction_distance": True,
        "blockade_distance": True,
        "swap_conflicts": True,
    }
    for T in range(MIN_STEPS, MAX_STEPS + 1):
        atom_x = []
        atom_y = []
        for i in range(N):
            atom_x.append([Int(f"a{i}_x_{t}") for t in range(T + 1)])
            atom_y.append([Int(f"a{i}_y_{t}") for t in range(T + 1)])
        r = []
        c = []
        for t in range(T + 1):
            r.append([(Int(f"r_{i}_{t}"), Bool(f"r_{i}_{t}_on")) for i in range(r_max)])
            c.append([(Int(f"c_{i}_{t}"), Bool(f"c_{i}_{t}_on")) for i in range(c_max)])
        s = Solver()
        if use_constraints["atom_bounds"]:
            add_atom_bounds(s, atom_x, atom_y, W, H)
        if use_constraints["active_line_bounds"]:
            add_active_line_bounds(s, r, c, W, H)
        if use_constraints["initial_lines_off"]:
            add_initial_lines_off(s, r, c)
        if use_constraints["initial_atom_positions"]:
            add_initial_atom_positions(s, atom_x, atom_y, starts)
        if use_constraints["line_speed_limit"]:
            add_line_speed_limit(s, r, c)
        if use_constraints["line_order"]:
            add_line_order(s, r, c)
        if use_constraints["no_motion_during_switch"]:
            add_no_motion_during_switch(s, r, c)
        if use_constraints["captured_atom_motion"]:
            add_captured_atom_motion(s, atom_x, atom_y, r, c)
        if use_constraints["uncaptured_atom_wait"]:
            add_uncaptured_atom_wait(s, atom_x, atom_y, r, c)
        if use_constraints["vertex_conflicts"]:
            add_vertex_conflicts(s, atom_x, atom_y)
        if use_constraints["interaction_distance"]:
            add_interaction_distance(s, atom_x, atom_y, cz_set, r_int)
        if use_constraints["blockade_distance"]:
            add_blockade_distance(s, atom_x, atom_y, cz_set, r_block)
        if use_constraints["swap_conflicts"]:
            add_swap_conflicts(s, atom_x, atom_y)
        if s.check() == sat:
            m = s.model()
            print(f"Solution found in {T} steps:")
            rows_by_step, columns_by_step = ([], [])
            for t in range(T + 1):
                print(f"t={t}:")
                for i in range(N):
                    print(
                        f"      Atom {i} ({m.eval(atom_x[i][t], model_completion=True)}, {m.eval(atom_y[i][t], model_completion=True)})"
                    )
                active_rows = [
                    (j, m.eval(r[t][j][0], model_completion=True).as_long())
                    for j in range(r_max)
                    if is_true(m.eval(r[t][j][1], model_completion=True))
                ]
                active_cols = [
                    (j, m.eval(c[t][j][0], model_completion=True).as_long())
                    for j in range(c_max)
                    if is_true(m.eval(c[t][j][1], model_completion=True))
                ]
                rows_by_step.append([y for _, y in active_rows])
                columns_by_step.append([x for _, x in active_cols])
                print(
                    f"      Active AOD rows (id, y): {active_rows}; AOD columns (id, x): {active_cols}"
                )
            solver_paths = [
                [
                    (
                        m.eval(atom_x[i][t], model_completion=True).as_long(),
                        m.eval(atom_y[i][t], model_completion=True).as_long(),
                    )
                    for t in range(T + 1)
                ]
                for i in range(N)
            ]
            solver_moves = [
                sum((p != q for p, q in zip(path, path[1:]))) for path in solver_paths
            ]
            for i, moves in enumerate(solver_moves):
                print(f"Atom {i}: movements = {moves}")
            print(f"Total atom movements: {sum(solver_moves)}")
            if animate:
                animate_atom_paths(
                    [[0] * W for _ in range(H)],
                    solver_paths,
                    marked_cells=[],
                    rows=rows_by_step,
                    columns=columns_by_step,
                    fps=2,
                    output_path=str(Path(output_dir) / "cz_interactions.mp4"),
                )
            break
        else:
            print(f"For T={T}: no solution found.")
    end = time.time()
    print(f"Execution time: {round(end - start)} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Save an English figure or MP4; MP4 needs ffmpeg.",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Directory for optional figures and animations."
    )
    args = parser.parse_args()
    result = main(animate=args.animate, output_dir=args.output_dir)
