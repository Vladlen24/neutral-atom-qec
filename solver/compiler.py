"""Support alternative target configurations with SAT routing.

Reconstructed research stage; see README.md for formulas and assumptions.
"""

import argparse
from pathlib import Path
import time
from z3 import And, Int, Not, Or, Solver, sat


def main(animate=False, output_dir=None):
    """Solve the original example; edit the architecture and program parameters below."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent / "output"
    if animate:
        if __package__:
            from .visualization import animate_atom_paths, plot_atom_paths
        else:
            from visualization import animate_atom_paths, plot_atom_paths
    MIN_STEPS = 4
    MAX_STEPS = 20
    W, H = (7, 7)
    starts = [(0, 0), (0, 6)]
    N = len(starts)
    targets = [[(1, 2), (2, 2)], [(1, 4), (2, 4)]]
    for T in range(MIN_STEPS, MAX_STEPS):
        atom_x = []
        atom_y = []
        for i in range(N):
            atom_x.append([Int(f"a{i}_x_{t}") for t in range(T + 1)])
            atom_y.append([Int(f"a{i}_y_{t}") for t in range(T + 1)])
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
        for i in range(N):
            s.add(atom_x[i][0] == starts[i][0], atom_y[i][0] == starts[i][1])
        s.add(
            Or(
                [
                    Or(
                        And(
                            atom_x[0][T] == pos_A[0],
                            atom_y[0][T] == pos_A[1],
                            atom_x[1][T] == pos_B[0],
                            atom_y[1][T] == pos_B[1],
                        ),
                        And(
                            atom_x[0][T] == pos_B[0],
                            atom_y[0][T] == pos_B[1],
                            atom_x[1][T] == pos_A[0],
                            atom_y[1][T] == pos_A[1],
                        ),
                    )
                    for pos_A, pos_B in targets
                ]
            )
        )
        for t in range(T):
            for ax, ay in zip(atom_x, atom_y):
                dx = ax[t + 1] - ax[t]
                dy = ay[t + 1] - ay[t]
                s.add(
                    Or(
                        And(dx == 0, dy == 0),
                        And(dx == 0, dy == 1),
                        And(dx == 0, dy == -1),
                        And(dx == 1, dy == 0),
                        And(dx == -1, dy == 0),
                    )
                )
        for t in range(T + 1):
            for i in range(N):
                for j in range(i + 1, N):
                    s.add(
                        Or(atom_x[i][t] != atom_x[j][t], atom_y[i][t] != atom_y[j][t])
                    )
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
            for t in range(T + 1):
                print(f"t={t}:")
                for i in range(N):
                    print(f"      Atom {i} ({m[atom_x[i][t]]}, {m[atom_y[i][t]]})")
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
                    marked_cells=[cell for group in targets for cell in group],
                    output_path=str(Path(output_dir) / "alternative_targets.mp4"),
                )
            break
        else:
            print(f"UNSAT: no solution ({T} steps may be insufficient).")


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
