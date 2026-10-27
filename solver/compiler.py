"""Schedule local, global, and CZ gate layers with continuous AOD state."""

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
        add_interaction_distance,
        add_blockade_distance,
        add_selected_pair_count,
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
        add_interaction_distance,
        add_blockade_distance,
        add_selected_pair_count,
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
    "r_int": 1,
    "r_block": 3,
}
DEFAULT_GATES = [
    (0, ("rx", pi / 2)),
    (3, ("rz", pi / 4)),
    (0, 2),
    (1, 3),
    (0, ("rx", -pi / 2)),
    (1, ("rz", pi / 4)),
    ("global", ("ry", pi / 2)),
    (0, 4),
    (1, 2),
    (0, ("rz", pi / 2)),
    (1, ("rx", pi / 2)),
    ("global", ("ry", pi)),
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
    "interaction_distance": True,
    "blockade_distance": True,
    "crosstalk_distance": True,
    "preserve_gate_order": True,
}
LAYER_PRIORITY = ("local", "rydberg")


# Operation indexing and candidate selection
# ========================================================================
def index_gate_operations(gate_seq, atom_count):
    """Index CZ, local, and global gates, retaining every occurrence and its ID."""

    def valid_atom(atom):
        return (
            isinstance(atom, int)
            and (not isinstance(atom, bool))
            and (0 <= atom < atom_count)
        )

    operations = []
    for operation_id, gate in enumerate(gate_seq):
        if not isinstance(gate, (tuple, list)) or len(gate) != 2:
            raise ValueError(
                f"Operation {operation_id}: expected CZ (i, j) or (atom, (axis, angle))."
            )
        target, payload = gate
        if isinstance(payload, int) and (not isinstance(payload, bool)):
            if not valid_atom(target) or not valid_atom(payload) or target == payload:
                raise ValueError(f"Operation {operation_id}: invalid CZ pair {gate}.")
            layer_type = "rydberg"
            targets = tuple(sorted((target, payload)))
            canonical_gate = targets
        else:
            if (
                not isinstance(payload, (tuple, list))
                or len(payload) != 2
                or payload[0] not in ("rx", "ry", "rz")
            ):
                raise ValueError(
                    f"Operation {operation_id}: expected rx, ry, or rz and an angle."
                )
            if target == "global":
                layer_type, targets = ("global", tuple(range(atom_count)))
            elif valid_atom(target):
                layer_type, targets = ("local", (target,))
            else:
                raise ValueError(f"Operation {operation_id}: invalid atom {target}.")
            canonical_gate = (target, tuple(payload))
        operations.append(
            {
                "id": operation_id,
                "type": layer_type,
                "targets": targets,
                "gate": canonical_gate,
            }
        )
    return operations


def get_layer_candidates(remaining_operations):
    """Find ready operations across all types, giving local rotations strict priority."""
    if not remaining_operations:
        return (None, [])
    if remaining_operations[0]["type"] == "global":
        return ("global", remaining_operations[:1])
    ready = []
    encountered_atoms = set()
    for operation in remaining_operations:
        if operation["type"] == "global":
            break
        if encountered_atoms.isdisjoint(operation["targets"]):
            ready.append(operation)
        encountered_atoms.update(operation["targets"])
    for layer_type in LAYER_PRIORITY:
        candidates = [
            operation for operation in ready if operation["type"] == layer_type
        ]
        if candidates:
            return (layer_type, candidates)
    raise ValueError("No layer type is configured for the ready operations.")


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
    r_int, r_block = (config["r_int"], config["r_block"])

    # Shared transport constraints
    # ========================================================================
    def add_transport_constraints(
        s, atom_x, atom_y, r, c, current_starts, initial_rows, initial_cols
    ):
        """Apply the same transport and trap-support constraints to every layer type."""
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
        """Validate initial transport state without interaction constraints."""
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

    # Layer-specific constraints
    # ========================================================================
    def add_local_layer_constraints(
        s, atom_x, atom_y, candidates, count, enabled, layer_index
    ):
        targets = {operation["id"]: operation["targets"][0] for operation in candidates}
        isolated = (
            local_gate_isolation(atom_x, atom_y, targets, r_crosstalk)
            if "crosstalk_distance" in enabled
            else {operation_id: BoolVal(True) for operation_id in targets}
        )
        if count == len(candidates):
            s.add(*isolated.values())
        else:
            s.add(PbGe([(condition, 1) for condition in isolated.values()], count))
        return isolated

    def add_rydberg_layer_constraints(
        s, atom_x, atom_y, candidates, count, enabled, layer_index
    ):
        chosen = {
            operation["id"]: Bool(f"M{layer_index}_g{operation['id']}_chosen")
            for operation in candidates
        }
        add_selected_pair_count(s, chosen, count)
        chosen_by_pair = {
            operation["gate"]: chosen[operation["id"]] for operation in candidates
        }
        pairs = set(chosen_by_pair)
        if "interaction_distance" in enabled:
            add_interaction_distance(s, atom_x, atom_y, pairs, r_int, chosen_by_pair)
        if "blockade_distance" in enabled:
            add_blockade_distance(s, atom_x, atom_y, pairs, r_block, chosen_by_pair)
        return chosen

    # Layer settings
    # ========================================================================
    layer_settings = {
        "local": {
            "min_steps": 2,
            "max_steps": 10,
            "constraints": ("crosstalk_distance",),
            "build_constraints": add_local_layer_constraints,
        },
        "rydberg": {
            "min_steps": 2,
            "max_steps": 10,
            "constraints": ("interaction_distance", "blockade_distance"),
            "build_constraints": add_rydberg_layer_constraints,
        },
        "global": {
            "min_steps": 0,
            "max_steps": 0,
            "constraints": (),
            "build_constraints": None,
        },
    }
    for kind, options in layer_overrides.items():
        layer_settings[kind].update(options)

    # Single-layer solver
    # ========================================================================
    def solve_next_layer(
        current_starts, remaining_operations, initial_rows, initial_cols, layer_index
    ):
        layer_type, candidates = get_layer_candidates(remaining_operations)
        if not candidates:
            return None
        settings = layer_settings[layer_type]
        if layer_type == "global":
            return (
                layer_type,
                0,
                candidates,
                remaining_operations[1:],
                [[position] for position in current_starts],
                [list(initial_rows)],
                [list(initial_cols)],
            )
        enabled = {name for name in settings["constraints"] if use_constraints[name]}
        atom_count = len(current_starts)
        print(
            f"Layer {layer_index} ({layer_type}): candidates {[op['id'] for op in candidates]}"
        )
        for count in range(len(candidates), 0, -1):
            for T in range(settings["min_steps"], settings["max_steps"] + 1):
                atom_x = [
                    [Int(f"M{layer_index}_a{i}_x_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                atom_y = [
                    [Int(f"M{layer_index}_a{i}_y_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                r = [
                    [
                        (
                            Int(f"M{layer_index}_r_{j}_{t}"),
                            Bool(f"M{layer_index}_r_{j}_{t}_on"),
                        )
                        for j in range(r_max)
                    ]
                    for t in range(T + 1)
                ]
                c = [
                    [
                        (
                            Int(f"M{layer_index}_c_{j}_{t}"),
                            Bool(f"M{layer_index}_c_{j}_{t}_on"),
                        )
                        for j in range(c_max)
                    ]
                    for t in range(T + 1)
                ]
                s = Solver()
                add_transport_constraints(
                    s, atom_x, atom_y, r, c, current_starts, initial_rows, initial_cols
                )
                selection = settings["build_constraints"](
                    s, atom_x, atom_y, candidates, count, enabled, layer_index
                )
                result = s.check()
                if result == unsat:
                    print(
                        f"Layer {layer_index} ({layer_type}), K={count}, T={T}: UNSAT"
                    )
                    continue
                if result == unknown:
                    raise RuntimeError(
                        f"Layer {layer_index} ({layer_type}), K={count}, T={T}: UNKNOWN ({s.reason_unknown()})"
                    )
                model = s.model()
                selected = [
                    operation
                    for operation in candidates
                    if is_true(
                        model.eval(selection[operation["id"]], model_completion=True)
                    )
                ][:count]
                selected_ids = {operation["id"] for operation in selected}
                deferred = [
                    operation
                    for operation in remaining_operations
                    if operation["id"] not in selected_ids
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
                return (
                    layer_type,
                    T,
                    selected,
                    deferred,
                    paths,
                    row_states,
                    col_states,
                )
        return None

    # Successive layers with continuous AOD state
    # ========================================================================
    if not starts:
        raise ValueError("At least one atom is required.")
    if not use_constraints["preserve_gate_order"]:
        raise ValueError("The mixed pipeline preserves gate order on each atom.")
    if not 0 <= r_int < r_block or r_crosstalk < 0:
        raise ValueError("Require 0 <= r_int < r_block and r_crosstalk >= 0.")
    for settings in layer_settings.values():
        if not 0 <= settings["min_steps"] <= settings["max_steps"]:
            raise ValueError(
                "Require 0 <= min_steps <= max_steps for every layer type."
            )
    if (
        layer_settings["global"]["min_steps"],
        layer_settings["global"]["max_steps"],
    ) != (0, 0):
        raise ValueError(
            "Global rotations require no transport: their T range must be 0..0."
        )
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
            layer_type, candidates = get_layer_candidates(remaining_operations)
            settings = layer_settings[layer_type]
            raise RuntimeError(
                f"Layer {layer_index} ({layer_type}): UNSAT for all K and T={settings['min_steps']}..{settings['max_steps']}; candidates {[op['id'] for op in candidates]}. Automatic fallback to another layer type is disabled."
            )
        layer_type, T, selected, deferred, paths, row_states, col_states = layer
        for i, path in enumerate(paths):
            all_paths[i].extend(path[1:])
        all_rows.extend(
            [[position for position, on in state if on] for state in row_states[1:]]
        )
        all_cols.extend(
            [[position for position, on in state if on] for state in col_states[1:]]
        )
        total_steps += T
        selected_ids = [operation["id"] for operation in selected]
        selected_gates = [operation["gate"] for operation in selected]
        gate_layers.append(
            {
                "layer": layer_index,
                "type": layer_type,
                "step": total_steps,
                "transport_steps": T,
                "operation_ids": selected_ids,
                "gates": selected_gates,
            }
        )
        operation_layers.append((total_steps, selected_ids))
        current_starts = [path[-1] for path in paths]
        initial_rows = row_states[-1]
        initial_cols = col_states[-1]
        remaining_operations = deferred
        print(
            f"Layer {layer_index} ({layer_type}): T={T}, executed {list(zip(selected_ids, selected_gates))}"
        )
    print(
        f"All gates completed. Layers: {len(gate_layers)}; transport steps: {total_steps}."
    )
    print(f"Layer types: {[event['type'] for event in gate_layers]}")
    print(f"Execution time: {time.time() - pipeline_start:.2f} s")
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
            output_path=destination / "mixed_gate_layers.mp4",
            preview_path=destination / "mixed_gate_layers.png",
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
