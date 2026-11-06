"""Schedule gate layers using SLM placements, without transport variables."""

import argparse
import json
import time
from math import isfinite, pi
from pathlib import Path

from z3 import (
    Abs,
    And,
    Bool,
    Implies,
    Int,
    Not,
    Or,
    PbEq,
    PbGe,
    Solver,
    is_true,
    sat,
    unknown,
)

if __package__:
    from .compiler import get_layer_candidates, index_gate_operations
else:
    from compiler import get_layer_candidates, index_gate_operations


# Architecture and input gates
# ========================================================================
DEFAULT_ARCHITECTURE = {
    "width": 8,
    "height": 7,
    "slm_sites": [
        (x + offset, y)
        for y in range(0, 7, 2)
        for x in range(0, 7, 3)
        for offset in (0, 1)
    ],
    "starts": [
        (1, 0),
        (3, 0),
        (6, 0),
        (1, 2),
        (3, 2),
        (6, 2),
        (1, 4),
        (3, 4),
        (6, 4),
        (1, 6),
    ],
    "r_int": 1,
    "r_block": 3,
    "r_crosstalk": 2,
}
DEFAULT_GATES = [
    ("global", ("ry", pi / 2)),
    (7, 0),
    (8, 1),
    (9, 2),
    (7, 1),
    (8, 0),
    (9, 4),
    (7, 2),
    (8, 4),
    (9, 0),
    (7, 3),
    (8, 5),
    (9, 6),
    ("global", ("ry", -pi / 2)),
]


# Placement constraints
# ========================================================================
def add_slm_placement(solver, x, y, sites):
    """Hold every atom in a distinct SLM trap, including spectator atoms."""
    for i in range(len(x)):
        solver.add(Or(*[And(x[i] == sx, y[i] == sy) for sx, sy in sites]))
        for j in range(i):
            solver.add(Or(x[i] != x[j], y[i] != y[j]))


def distance(x, y, i, j):
    return Abs(x[i] - x[j]) + Abs(y[i] - y[j])


def add_local_constraints(solver, x, y, candidates, count, config):
    isolated = {
        op["id"]: And(
            *[
                distance(x, y, op["targets"][0], j) >= config["r_crosstalk"]
                for j in range(len(x))
                if j != op["targets"][0]
            ]
        )
        for op in candidates
    }
    solver.add(PbGe([(condition, 1) for condition in isolated.values()], count))
    return isolated


def add_rydberg_constraints(solver, x, y, candidates, count, config):
    chosen = {op["id"]: Bool(f"chosen_{op['id']}") for op in candidates}
    solver.add(PbEq([(condition, 1) for condition in chosen.values()], count))
    # Ready candidates have disjoint targets; repeated operations remain indexed.
    by_pair = {op["targets"]: chosen[op["id"]] for op in candidates}
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            d = distance(x, y, i, j)
            if (i, j) in by_pair:
                selected = by_pair[i, j]
                solver.add(Implies(selected, d <= config["r_int"]))
                solver.add(Implies(Not(selected), d >= config["r_block"]))
            else:
                solver.add(d >= config["r_block"])
    return chosen


LAYER_BUILDERS = {"local": add_local_constraints, "rydberg": add_rydberg_constraints}


# Input validation and placement pipeline
# ========================================================================
def validate_architecture(config):
    for key in ("width", "height"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer.")
    for key in ("slm_sites", "starts"):
        points = config[key]
        if not points or any(
            len(p) != 2 or any(type(v) is not int for v in p) for p in points
        ):
            raise ValueError(f"{key} must contain integer coordinate pairs.")
        if len(set(map(tuple, points))) != len(points):
            raise ValueError(f"{key} must not contain duplicate positions.")
    sites = set(map(tuple, config["slm_sites"]))
    if any(
        not (0 <= x < config["width"] and 0 <= y < config["height"]) for x, y in sites
    ):
        raise ValueError("SLM sites must lie inside the grid.")
    if not set(map(tuple, config["starts"])).issubset(sites):
        raise ValueError("Every initial atom must occupy a distinct SLM trap.")
    for key in ("r_int", "r_block", "r_crosstalk"):
        value = config[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{key} must be finite and nonnegative.")


def compile_placement(gate_seq, *, architecture=None, timeout_ms=0):
    """Maximize gates per layer; routing and movement costs are not evaluated.

    timeout_ms bounds each solver check (zero means unlimited). UNKNOWN
    stops compilation rather than being interpreted as a smaller feasible K.
    """
    config = {**DEFAULT_ARCHITECTURE, **(architecture or {})}
    validate_architecture(config)
    if type(timeout_ms) is not int or timeout_ms < 0:
        raise ValueError("timeout_ms must be a nonnegative integer.")
    remaining = index_gate_operations(gate_seq, len(config["starts"]))
    current = [tuple(p) for p in config["starts"]]
    layers, checks = [], []
    started = time.perf_counter()
    while remaining:
        layer_type, candidates = get_layer_candidates(remaining)
        if layer_type == "global":
            selected, positions = candidates, list(current)
        else:
            x = [Int(f"x_{i}") for i in range(len(current))]
            y = [Int(f"y_{i}") for i in range(len(current))]
            for count in range(len(candidates), 0, -1):
                solver = Solver()
                solver.set(timeout=timeout_ms)
                add_slm_placement(solver, x, y, config["slm_sites"])
                selection = LAYER_BUILDERS[layer_type](
                    solver, x, y, candidates, count, config
                )
                checked_at = time.perf_counter()
                result = solver.check()
                checks.append(
                    {
                        "layer": len(layers),
                        "type": layer_type,
                        "K": count,
                        "result": str(result),
                        "seconds": time.perf_counter() - checked_at,
                    }
                )
                if result == unknown:
                    raise RuntimeError(
                        f"Layer {len(layers)}, K={count}: UNKNOWN ({solver.reason_unknown()})."
                    )
                if result == sat:
                    model = solver.model()
                    selected = [
                        op
                        for op in candidates
                        if is_true(
                            model.eval(selection[op["id"]], model_completion=True)
                        )
                    ][:count]
                    positions = [
                        (model.eval(xi).as_long(), model.eval(yi).as_long())
                        for xi, yi in zip(x, y)
                    ]
                    break
            else:
                raise ValueError(
                    f"No feasible {layer_type} placement, even for K=1; ready operations: {[op['id'] for op in candidates]}."
                )
        layers.append(
            {
                "type": layer_type,
                "operations": selected,
                "positions": positions,
                "routing_verified": False,
            }
        )
        selected_ids = {op["id"] for op in selected}
        remaining = [op for op in remaining if op["id"] not in selected_ids]
        current = positions
    return {
        "model": "slm_placement",
        "architecture": config,
        "layers": layers,
        "routing_verified": False,
        "checks": checks,
        "seconds": time.perf_counter() - started,
    }


# Discrete placement snapshots: no trajectory interpolation
# ========================================================================
def render_placement_snapshots(
    schedule, output_dir="solver/output/placement", *, atom_roles=None
):
    """Save a contact sheet and a video of held snapshots, without motion paths."""
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, FFMpegWriter
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    config = schedule["architecture"]
    roles = (
        list(atom_roles) if atom_roles is not None else [None] * len(config["starts"])
    )
    if len(roles) != len(config["starts"]) or any(
        role not in (None, "data", "ancilla") for role in roles
    ):
        raise ValueError("atom_roles must assign data, ancilla, or None to each atom.")
    role_colors = {None: "white", "data": "#d62728", "ancilla": "#1f77b4"}
    legend = [
        Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            markerfacecolor=role_colors[role],
            markeredgecolor="black",
            label=label,
            markersize=9,
        )
        for role, label in (("data", "Data qubits"), ("ancilla", "Ancilla qubits"))
        if role in roles
    ]
    frames = [
        {"type": "initial", "operations": [], "positions": config["starts"]}
    ] + schedule["layers"]

    def draw(ax, index):
        ax.clear()
        frame = frames[index]
        kind = frame["type"]
        if kind in ("global", "rydberg"):
            ax.add_patch(
                Rectangle(
                    (-0.5, -0.5),
                    config["width"],
                    config["height"],
                    facecolor="green" if kind == "global" else "orange",
                    alpha=0.16,
                )
            )
        for sx, sy in config["slm_sites"]:
            ax.add_patch(
                Rectangle(
                    (sx - 0.4, sy - 0.4),
                    0.8,
                    0.8,
                    fill=False,
                    edgecolor="seagreen",
                    linewidth=1.2,
                )
            )
        if kind == "local":
            for op in frame["operations"]:
                x, y = frame["positions"][op["targets"][0]]
                ax.add_patch(
                    Rectangle(
                        (x - 0.45, y - 0.45),
                        0.9,
                        0.9,
                        facecolor="royalblue",
                        alpha=0.25,
                    )
                )
        if kind == "rydberg":
            for op in frame["operations"]:
                first, second = (frame["positions"][i] for i in op["targets"])
                ax.plot(
                    [first[0], second[0]],
                    [first[1], second[1]],
                    color="darkorange",
                    linewidth=3,
                )
        for atom, (x, y) in enumerate(frame["positions"]):
            ax.scatter(
                [x],
                [y],
                s=180,
                color=role_colors[roles[atom]],
                edgecolor="black",
                zorder=3,
            )
            ax.text(
                x,
                y,
                str(atom),
                ha="center",
                va="center",
                fontsize=8,
                color="black" if roles[atom] is None else "white",
                zorder=4,
            )
        ids = [op["id"] for op in frame["operations"]]
        ax.set_title(
            (
                "Initial placement"
                if index == 0
                else f"Layer {index}: {kind} | gates {ids}"
            ),
            fontsize=9,
        )
        ax.set(
            xlim=(-0.5, config["width"] - 0.5),
            ylim=(-0.5, config["height"] - 0.5),
            aspect="equal",
        )
        ax.set_xticks(range(config["width"]))
        ax.set_yticks(range(config["height"]))
        ax.grid(alpha=0.15)

    columns = min(3, len(frames))
    rows = (len(frames) + columns - 1) // columns
    sheet, axes = plt.subplots(
        rows, columns, figsize=(4 * columns, 4 * rows), squeeze=False
    )
    for index, ax in enumerate(axes.flat):
        draw(ax, index) if index < len(frames) else ax.set_visible(False)
    sheet.suptitle(
        "SLM placements — routing not evaluated; orange links denote CZ gates"
    )
    if legend:
        sheet.legend(handles=legend, loc="lower center", ncol=len(legend))
    sheet.tight_layout(rect=(0, 0.025 if legend else 0, 1, 0.96))
    preview = directory / "placements.png"
    sheet.savefig(preview, dpi=140)
    plt.close(sheet)

    fig, ax = plt.subplots(figsize=(7, 6))
    fig.suptitle("Placement snapshots — no trajectories or physical timing")
    if legend:
        fig.legend(handles=legend, loc="lower center", ncol=len(legend))
        fig.subplots_adjust(bottom=0.12)
    animation = FuncAnimation(
        fig, lambda i: draw(ax, i), frames=len(frames), interval=1000, repeat=False
    )
    video = directory / "placements.mp4"
    animation.save(video, writer=FFMpegWriter(fps=1), dpi=120)
    plt.close(fig)
    return {"preview": str(preview), "video": str(video)}


# Command-line entry point
# ========================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Export placement snapshots as PNG and MP4.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("solver/output/placement")
    )
    parser.add_argument("--timeout-ms", type=int, default=0)
    args = parser.parse_args()
    schedule = compile_placement(DEFAULT_GATES, timeout_ms=args.timeout_ms)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "schedule.json").write_text(
        json.dumps(schedule, indent=2) + "\n"
    )
    for index, layer in enumerate(schedule["layers"], 1):
        print(
            f"Layer {index}: {layer['type']}, operations {[op['id'] for op in layer['operations']]}"
        )
    print(
        f"{len(schedule['layers'])} layers, {len(schedule['checks'])} solver checks, {schedule['seconds']:.3f} s; routing not evaluated."
    )
    if args.animate:
        print(render_placement_snapshots(schedule, args.output_dir))


if __name__ == "__main__":
    main()
