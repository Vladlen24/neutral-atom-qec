"""Introductory Z3 examples: a Latin square, graph coloring, and a maze."""

from z3 import And, Distinct, Int, Not, Or, Solver, sat


def sudoku_example():
    X = [[Int(f"x_{i}_{j}") for i in range(4)] for j in range(4)]
    s = Solver()
    for i in range(4):
        for j in range(4):
            s.add(X[i][j] >= 1, X[i][j] <= 4)
    for i in range(4):
        s.add(Distinct(X[i]))
        s.add(Distinct([X[j][i] for j in range(4)]))
    s.add(X[0][0] == 1, X[1][2] == 3)
    if s.check() == sat:
        m = s.model()
        for i in range(4):
            print([m.evaluate(X[i][j]) for j in range(4)])
    else:
        print("UNSAT: no solution.")


def coloring_example():
    r = [Int(f"r_{i}") for i in range(5)]
    s = Solver()
    for i in range(5):
        s.add(r[i] >= 1, r[i] <= 3)
    connectivity_map = [
        [0, 0, 1, 1, 0],
        [0, 0, 1, 0, 1],
        [1, 1, 0, 1, 1],
        [1, 0, 1, 0, 1],
        [0, 1, 1, 1, 0],
    ]
    for i in range(5):
        s.add([r[i] != r[j] for j in range(5) if connectivity_map[i][j] == 1])
    if s.check() == sat:
        m = s.model()
        print([m.evaluate(r[i]) for i in range(5)])
    else:
        print("UNSAT: no solution.")


def maze_example():
    W = 10
    H = 10
    start_x = 0
    start_y = 0
    finish_x = H - 1
    finish_y = W - 1
    MAX_STEPS = W * H // 2
    walls = [
        (0, 3),
        (1, 0),
        (1, 1),
        (1, 3),
        (1, 5),
        (1, 6),
        (1, 7),
        (1, 8),
        (2, 8),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (3, 6),
        (3, 8),
        (4, 6),
        (5, 0),
        (5, 1),
        (5, 2),
        (5, 3),
        (5, 4),
        (5, 6),
        (5, 7),
        (5, 8),
        (7, 1),
        (7, 2),
        (7, 3),
        (7, 4),
        (7, 5),
        (7, 6),
        (7, 7),
        (7, 8),
        (7, 9),
        (9, 0),
        (9, 1),
        (9, 2),
        (9, 3),
        (9, 4),
        (9, 5),
        (9, 6),
        (9, 7),
    ]
    wall_cells = set(walls)

    def draw_maze(path=()):
        path_cells = set(path)
        for x in range(H):
            print(
                "".join(
                    (
                        "S"
                        if (x, y) == (start_x, start_y)
                        else "F"
                        if (x, y) == (finish_x, finish_y)
                        else "#"
                        if (x, y) in wall_cells
                        else "*"
                        if (x, y) in path_cells
                        else "."
                        for y in range(W)
                    )
                )
            )

    print("Maze before solving (S = start, F = finish, # = wall):")
    draw_maze()
    is_solution = False
    for N in range(1, MAX_STEPS + 1):
        X = [Int(f"x_{i}") for i in range(N)]
        Y = [Int(f"y_{i}") for i in range(N)]
        s = Solver()
        s.add(X[0] == start_x, Y[0] == start_y)
        s.add(X[N - 1] == finish_x, Y[N - 1] == finish_y)
        for k in range(N - 1):
            s.add(
                Or(
                    And(X[k + 1] == X[k] + 1, Y[k + 1] == Y[k]),
                    And(X[k + 1] == X[k] - 1, Y[k + 1] == Y[k]),
                    And(X[k + 1] == X[k], Y[k + 1] == Y[k] + 1),
                    And(X[k + 1] == X[k], Y[k + 1] == Y[k] - 1),
                )
            )
        for k in range(N):
            s.add(Not(Or([And(X[k] == wx, Y[k] == wy) for wx, wy in walls])))
            s.add(X[k] >= 0, X[k] < H)
            s.add(Y[k] >= 0, Y[k] < W)
        for i in range(N):
            for j in range(i + 1, N):
                s.add(Or(X[i] != X[j], Y[i] != Y[j]))
        if s.check() == sat:
            m = s.model()
            print(f"\nSolution ({N} cells):")
            path = [
                (m.evaluate(X[k]).as_long(), m.evaluate(Y[k]).as_long())
                for k in range(N)
            ]
            print(path)
            print("Maze with the solution (* = path):")
            draw_maze(path)
            is_solution = True
            break
    if not is_solution:
        print("UNSAT: no solution.")


if __name__ == "__main__":
    print("Sudoku-style Latin square")
    sudoku_example()
    print("Graph coloring")
    coloring_example()
    print("Maze path finding")
    maze_example()
