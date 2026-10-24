"""Add CZ interaction and isolation distance constraints.

Reconstructed research stage; see README.md for formulas and assumptions.
"""

import argparse
from pathlib import Path
import time
from z3 import Abs, And, Bool, Implies, Int, Not, Or, Solver, is_true, sat


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
        for i in range(N):
            for t in range(T + 1):
                s.add(
                    And(
                        atom_x[i][t] >= 0,
                        atom_x[i][t] < W,
                        atom_y[i][t] >= 0,
                        atom_y[i][t] < H,
                    )
                )
        for t in range(T + 1):
            for i in range(r_max):
                s.add(Implies(r[t][i][1], And(r[t][i][0] >= 0, r[t][i][0] < H)))
            for i in range(c_max):
                s.add(Implies(c[t][i][1], And(c[t][i][0] >= 0, c[t][i][0] < W)))
        for _, enabled in r[0] + c[0]:
            s.add(Not(enabled))
        for i in range(N):
            s.add(atom_x[i][0] == starts[i][0], atom_y[i][0] == starts[i][1])
        for t in range(T):
            for j in range(r_max):
                s.add(
                    Implies(
                        And(r[t][j][1], r[t + 1][j][1]),
                        Abs(r[t + 1][j][0] - r[t][j][0]) <= 1,
                    )
                )
            for j in range(c_max):
                s.add(
                    Implies(
                        And(c[t][j][1], c[t + 1][j][1]),
                        Abs(c[t + 1][j][0] - c[t][j][0]) <= 1,
                    )
                )
            for lines, count in ((r, r_max), (c, c_max)):
                for i in range(count):
                    for j in range(i + 1, count):
                        both_on = And(
                            lines[t][i][1],
                            lines[t][j][1],
                            lines[t + 1][i][1],
                            lines[t + 1][j][1],
                        )
                        s.add(
                            Implies(
                                And(both_on, lines[t][i][0] < lines[t][j][0]),
                                lines[t + 1][i][0] < lines[t + 1][j][0],
                            )
                        )
                        s.add(
                            Implies(
                                And(both_on, lines[t][i][0] > lines[t][j][0]),
                                lines[t + 1][i][0] > lines[t + 1][j][0],
                            )
                        )
            switching = Or(
                *[r[t][j][1] != r[t + 1][j][1] for j in range(r_max)],
                *[c[t][j][1] != c[t + 1][j][1] for j in range(c_max)],
            )
            row_motion = Or(
                *[
                    And(r[t][j][1], r[t + 1][j][1], r[t][j][0] != r[t + 1][j][0])
                    for j in range(r_max)
                ]
            )
            col_motion = Or(
                *[
                    And(c[t][j][1], c[t + 1][j][1], c[t][j][0] != c[t + 1][j][0])
                    for j in range(c_max)
                ]
            )
            s.add(Implies(switching, And(Not(row_motion), Not(col_motion))))
            for i in range(N):
                captured_by = []
                for j in range(r_max):
                    for k in range(c_max):
                        captured = And(
                            r[t][j][1],
                            c[t][k][1],
                            atom_y[i][t] == r[t][j][0],
                            atom_x[i][t] == c[t][k][0],
                        )
                        captured_by.append(captured)
                        s.add(
                            Implies(
                                And(Not(switching), captured),
                                And(
                                    atom_y[i][t + 1] == r[t + 1][j][0],
                                    atom_x[i][t + 1] == c[t + 1][k][0],
                                ),
                            )
                        )
                s.add(
                    Implies(
                        Or(switching, Not(Or(*captured_by))),
                        And(
                            atom_x[i][t + 1] == atom_x[i][t],
                            atom_y[i][t + 1] == atom_y[i][t],
                        ),
                    )
                )
        for t in range(T + 1):
            for i in range(N):
                for j in range(i + 1, N):
                    s.add(
                        Or(atom_x[i][t] != atom_x[j][t], atom_y[i][t] != atom_y[j][t])
                    )
        for i in range(N):
            for j in range(i + 1, N):
                distance = Abs(atom_x[i][T] - atom_x[j][T]) + Abs(
                    atom_y[i][T] - atom_y[j][T]
                )
                if (i, j) in cz_set:
                    s.add(distance <= r_int)
                else:
                    s.add(distance >= r_block)
        for t in range(T):
            for i in range(N):
                for j in range(i + 1, N):
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
        if s.check() == sat:
            m = s.model()
            print(f"Solution found in {T} steps:")
            rows_by_step, columns_by_step = ([], [])
            for t in range(T + 1):
                print(f"t={t}:")
                for i in range(N):
                    print(f"      Atom {i} ({m[atom_x[i][t]]}, {m[atom_y[i][t]]})")
                active_rows = [
                    (j, m.eval(r[t][j][0]).as_long())
                    for j in range(r_max)
                    if is_true(m.eval(r[t][j][1]))
                ]
                active_cols = [
                    (j, m.eval(c[t][j][0]).as_long())
                    for j in range(c_max)
                    if is_true(m.eval(c[t][j][1]))
                ]
                rows_by_step.append([y for _, y in active_rows])
                columns_by_step.append([x for _, x in active_cols])
                print(
                    f"      Active AOD rows (id, y): {active_rows}; AOD columns (id, x): {active_cols}"
                )
            solver_paths = [
                [
                    (m[atom_x[i][t]].as_long(), m[atom_y[i][t]].as_long())
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
