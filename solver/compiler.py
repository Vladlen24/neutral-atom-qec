"""Schedule single-qubit rotations with continuous AOD state."""

import argparse
import json
import time
from math import pi
from pathlib import Path
from z3 import Bool, BoolVal, Int, IntVal, PbGe, Solver, is_true, sat, unknown, unsat

if __package__:
    from .constraints import (
        add_active_line_bounds,
        add_atom_bounds,
        add_captured_atom_motion,
        add_initial_atom_positions,
        add_initial_line_state,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_swap_conflicts,
        add_trap_support,
        add_uncaptured_atom_wait,
        add_vertex_conflicts,
        local_gate_isolation,
    )
else:
    from constraints import (
        add_active_line_bounds,
        add_atom_bounds,
        add_captured_atom_motion,
        add_initial_atom_positions,
        add_initial_line_state,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_swap_conflicts,
        add_trap_support,
        add_uncaptured_atom_wait,
        add_vertex_conflicts,
        local_gate_isolation,
    )
# Example architecture and program
# ========================================================================
DEFAULT_ARCHITECTURE = {
    "width": 5,
    "height": 5,
    "starts": [(0, 0), (0, 1), (0, 2), (0, 3), (2, 0)],
    "slm_sites": [(0, 0), (0, 1), (0, 2), (0, 3), (2, 0), (1, 1), (3, 2), (4, 4)],
    "rows": 4,
    "columns": 4,
    "r_crosstalk": 2,
}
DEFAULT_GATES = [
    (0, ("rx", pi / 2)),
    (3, ("rz", pi / 4)),
    (0, ("rz", -pi / 2)),
    ("global", ("ry", pi / 2)),
    (1, ("rx", pi / 4)),
    (4, ("rz", -pi / 2)),
    ("global", ("ry", pi)),
    ("global", ("ry", pi / 4)),
]
DEFAULT_CONSTRAINTS = {
    "atom_bounds": True,
    "active_line_bounds": True,
    "initial_line_state": True,
    "initial_atom_positions": True,
    "line_speed_limit": True,
    "line_order": True,
    "no_motion_during_switch": True,
    "captured_atom_motion": True,
    "uncaptured_atom_wait": True,
    "vertex_conflicts": True,
    "swap_conflicts": True,
    "trap_support": True,
    "interaction_distance": False,
    "blockade_distance": False,
    "crosstalk_distance": True,
    "preserve_gate_order": True,
}


# Operation indexing and candidate selection
# ========================================================================
def index_gate_operations(gate_seq, atom_count):
    """Retain each gate occurrence; keep its axis and angle as operation metadata."""
    operations = []
    for operation_id, gate in enumerate(gate_seq):
        if not isinstance(gate, (tuple, list)) or len(gate) != 2:
            raise ValueError(
                f"Operation {operation_id}: expected (atom, (axis, angle))."
            )
        target, rotation = gate
        if target != "global" and (
            not isinstance(target, int)
            or isinstance(target, bool)
            or (not 0 <= target < atom_count)
        ):
            raise ValueError(f"Operation {operation_id}: invalid atom {target}.")
        if (
            not isinstance(rotation, (tuple, list))
            or len(rotation) != 2
            or rotation[0] not in ("rx", "ry", "rz")
        ):
            raise ValueError(
                f"Operation {operation_id}: expected rx, ry, or rz and an angle."
            )
        operations.append((operation_id, (target, tuple(rotation))))
    return operations


def get_layer_candidates(remaining_operations):
    """Select the first pending operation per atom before the next global rotation."""
    if not remaining_operations:
        return []
    if remaining_operations[0][1][0] == "global":
        return remaining_operations[:1]
    candidates = []
    encountered_atoms = set()
    for operation in remaining_operations:
        _, (target, rotation) = operation
        if target == "global":
            break
        if target not in encountered_atoms:
            candidates.append(operation)
            encountered_atoms.add(target)
    return candidates


# Compilation pipeline
# ========================================================================
def compile_schedule(
    gate_seq, *, architecture=None, layer_settings=None, use_constraints=None
):
    """Compile gate occurrences; optional dictionaries override example architecture and settings."""
    config = {**DEFAULT_ARCHITECTURE, **(architecture or {})}
    W, H = (config["width"], config["height"])
    starts = list(config["starts"])
    slm_sites = list(config["slm_sites"])
    r_max, c_max = (config["rows"], config["columns"])
    r_crosstalk = config["r_crosstalk"]
    use_constraints = {**DEFAULT_CONSTRAINTS, **(use_constraints or {})}
    layer_overrides = layer_settings or {}
    # Layer settings
    # ========================================================================
    layer_settings = {
        "local": {"min_steps": 2, "max_steps": 10},
        "global": {"min_steps": 0, "max_steps": 0},
    }
    for kind, options in layer_overrides.items():
        layer_settings[kind].update(options)
    MIN_STEPS, MAX_STEPS = (
        layer_settings["local"]["min_steps"],
        layer_settings["local"]["max_steps"],
    )
    if (
        layer_settings["global"]["min_steps"],
        layer_settings["global"]["max_steps"],
    ) != (0, 0):
        raise ValueError("Global rotations require T=0.")

    # Shared transport constraints
    # ========================================================================
    def add_transport_constraints(
        s, atom_x, atom_y, r, c, current_starts, initial_rows, initial_cols
    ):
        """Apply shared transport constraints without CZ distance constraints."""
        if use_constraints["atom_bounds"]:
            add_atom_bounds(s, atom_x, atom_y, W, H)
        if use_constraints["active_line_bounds"]:
            add_active_line_bounds(s, r, c, W, H)
        if use_constraints["initial_line_state"]:
            add_initial_line_state(s, r, c, initial_rows, initial_cols)
        if use_constraints["initial_atom_positions"]:
            add_initial_atom_positions(s, atom_x, atom_y, current_starts)
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
        if use_constraints["swap_conflicts"]:
            add_swap_conflicts(s, atom_x, atom_y)
        if use_constraints["trap_support"]:
            add_trap_support(s, atom_x, atom_y, r, c, slm_sites)

    def validate_initial_state(current_starts, initial_rows, initial_cols):
        """Validate the initial state, including empty programs and initial global rotations."""
        atom_x = [[IntVal(x)] for x, y in current_starts]
        atom_y = [[IntVal(y)] for x, y in current_starts]
        r = [
            [
                (IntVal(position if on else 0), BoolVal(on))
                for position, on in initial_rows
            ]
        ]
        c = [
            [
                (IntVal(position if on else 0), BoolVal(on))
                for position, on in initial_cols
            ]
        ]
        s = Solver()
        add_transport_constraints(
            s, atom_x, atom_y, r, c, current_starts, initial_rows, initial_cols
        )
        result = s.check()
        if result != sat:
            detail = s.reason_unknown() if result == unknown else "UNSAT"
            raise ValueError(f"Invalid initial state: {detail}.")

    # Single-layer solver
    # ========================================================================
    def solve_next_layer(
        current_starts, remaining_operations, initial_rows, initial_cols, layer_index
    ):
        candidates = get_layer_candidates(remaining_operations)
        if not candidates:
            return None
        if candidates[0][1][0] == "global":
            return (
                0,
                candidates,
                remaining_operations[1:],
                [[position] for position in current_starts],
                [list(initial_rows)],
                [list(initial_cols)],
            )
        atom_count = len(current_starts)
        print(f"Layer {layer_index}: local candidates (ID, gate): {candidates}")
        for gate_count in range(len(candidates), 0, -1):
            for T in range(MIN_STEPS, MAX_STEPS + 1):
                atom_x = [
                    [Int(f"SQ{layer_index}_a{i}_x_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                atom_y = [
                    [Int(f"SQ{layer_index}_a{i}_y_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                r = [
                    [
                        (
                            Int(f"SQ{layer_index}_r_{j}_{t}"),
                            Bool(f"SQ{layer_index}_r_{j}_{t}_on"),
                        )
                        for j in range(r_max)
                    ]
                    for t in range(T + 1)
                ]
                c = [
                    [
                        (
                            Int(f"SQ{layer_index}_c_{j}_{t}"),
                            Bool(f"SQ{layer_index}_c_{j}_{t}_on"),
                        )
                        for j in range(c_max)
                    ]
                    for t in range(T + 1)
                ]
                s = Solver()
                add_transport_constraints(
                    s, atom_x, atom_y, r, c, current_starts, initial_rows, initial_cols
                )
                targets = {
                    operation_id: target
                    for operation_id, (target, rotation) in candidates
                }
                isolated = (
                    local_gate_isolation(atom_x, atom_y, targets, r_crosstalk)
                    if use_constraints["crosstalk_distance"]
                    else {operation_id: BoolVal(True) for operation_id in targets}
                )
                if gate_count == len(candidates):
                    s.add(*isolated.values())
                else:
                    s.add(
                        PbGe(
                            [(condition, 1) for condition in isolated.values()],
                            gate_count,
                        )
                    )
                result = s.check()
                if result == unsat:
                    print(f"Layer {layer_index}, K={gate_count}, T={T}: UNSAT")
                    continue
                if result == unknown:
                    raise RuntimeError(
                        f"Layer {layer_index}, K={gate_count}, T={T}: UNKNOWN ({s.reason_unknown()})"
                    )
                model = s.model()
                admissible = [
                    operation
                    for operation in candidates
                    if is_true(
                        model.eval(isolated[operation[0]], model_completion=True)
                    )
                ]
                selected = admissible[:gate_count]
                selected_ids = {operation_id for operation_id, gate in selected}
                deferred = [
                    operation
                    for operation in remaining_operations
                    if operation[0] not in selected_ids
                ]
                paths = [
                    [
                        (
                            model.eval(atom_x[i][t], model_completion=True).as_long(),
                            model.eval(atom_y[i][t], model_completion=True).as_long(),
                        )
                        for t in range(T + 1)
                    ]
                    for i in range(atom_count)
                ]

                def read_line_state(lines, t):
                    state = []
                    for position, on in lines[t]:
                        enabled = is_true(model.eval(on, model_completion=True))
                        coordinate = (
                            model.eval(position, model_completion=True).as_long()
                            if enabled
                            else None
                        )
                        state.append((coordinate, enabled))
                    return state

                row_states = [read_line_state(r, t) for t in range(T + 1)]
                col_states = [read_line_state(c, t) for t in range(T + 1)]
                return (T, selected, deferred, paths, row_states, col_states)
        return None

    # Successive layers with continuous AOD state
    # ========================================================================
    if not starts:
        raise ValueError("At least one atom is required.")
    if not use_constraints["preserve_gate_order"]:
        raise ValueError("This single-qubit pipeline preserves gate order.")
    if use_constraints["interaction_distance"] or use_constraints["blockade_distance"]:
        raise ValueError("CZ distance constraints do not apply to single-qubit layers.")
    if not 0 <= MIN_STEPS <= MAX_STEPS or r_crosstalk < 0:
        raise ValueError("Require 0 <= min_steps <= max_steps and r_crosstalk >= 0.")
    pipeline_start = time.time()
    current_starts = list(starts)
    remaining_operations = index_gate_operations(gate_seq, len(starts))
    initial_rows = [(None, False) for _ in range(r_max)]
    initial_cols = [(None, False) for _ in range(c_max)]
    validate_initial_state(current_starts, initial_rows, initial_cols)
    all_paths = [[position] for position in current_starts]
    all_rows = [[position for position, on in initial_rows if on]]
    all_cols = [[position for position, on in initial_cols if on]]
    gate_layers = []
    operation_layers = []
    total_steps = 0
    while remaining_operations:
        layer_index = len(gate_layers) + 1
        layer = solve_next_layer(
            current_starts,
            remaining_operations,
            initial_rows,
            initial_cols,
            layer_index,
        )
        if layer is None:
            raise RuntimeError(
                f"Could not schedule local candidates within T={MIN_STEPS}..{MAX_STEPS}; remaining operations (ID, gate): {remaining_operations}"
            )
        T, selected, deferred, paths, row_states, col_states = layer
        layer_type = "global" if selected[0][1][0] == "global" else "local"
        for i, path in enumerate(paths):
            all_paths[i].extend(path[1:])
        all_rows.extend(
            [[position for position, on in state if on] for state in row_states[1:]]
        )
        all_cols.extend(
            [[position for position, on in state if on] for state in col_states[1:]]
        )
        total_steps += T
        selected_ids = [operation_id for operation_id, gate in selected]
        gate_layers.append(
            {
                "layer": layer_index,
                "type": layer_type,
                "step": total_steps,
                "transport_steps": T,
                "operation_ids": selected_ids,
                "gates": [gate for operation_id, gate in selected],
            }
        )
        operation_layers.append((total_steps, selected_ids))
        current_starts = [path[-1] for path in paths]
        initial_rows = row_states[-1]
        initial_cols = col_states[-1]
        remaining_operations = deferred
        print(
            f"Layer {layer_index} ({layer_type}): T={T}, executed operations (ID, gate): {selected}"
        )
        print(f"Deferred operations (ID, gate): {deferred}")
    print(
        f"All single-qubit gates completed. Layers: {len(gate_layers)}; transport steps: {total_steps}."
    )
    print(f"Single-qubit layers: {gate_layers}")
    print(f"Execution time: {round(time.time() - pipeline_start)} s")
    return {
        "architecture": config,
        "paths": all_paths,
        "rows": all_rows,
        "columns": all_cols,
        "layers": gate_layers,
        "operation_layers": operation_layers,
        "total_steps": total_steps,
    }


# Example output and visualization
# ========================================================================
def main(animate=False, output_dir=None):
    """Compile the supplied example and optionally save its video and preview."""
    result = compile_schedule(DEFAULT_GATES)
    if animate:
        if __package__:
            from .visualization import animate_atom_paths
        else:
            from visualization import animate_atom_paths
        destination = (
            Path(output_dir)
            if output_dir is not None
            else Path(__file__).resolve().parent / "output"
        )
        config = result["architecture"]
        animate_atom_paths(
            [[0] * config["width"] for _ in range(config["height"])],
            result["paths"],
            marked_cells=config["slm_sites"],
            rows=result["rows"],
            columns=result["columns"],
            gate_layers=result["layers"],
            fps=2,
            output_path=destination / "single_qubit_layers.mp4",
            preview_path=destination / "single_qubit_layers.png",
        )
    return result


# Command-line interface
# ========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Save an MP4 and a PNG preview; MP4 requires ffmpeg.",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Directory for generated videos and previews."
    )
    parser.add_argument(
        "--json", type=Path, help="Write the compiled schedule as JSON."
    )
    args = parser.parse_args()
    result = main(animate=args.animate, output_dir=args.output_dir)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n")
