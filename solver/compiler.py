"""Schedule successive CZ layers with continuous AOD state.

See README.md for the model, constraints, and scheduling priority.
"""

import argparse
from pathlib import Path
import time
import json
from z3 import Bool, Int, Or, PbLe, Solver, is_true, unknown, unsat

if __package__:
    from .constraints import (
        add_active_line_bounds,
        add_atom_bounds,
        add_blockade_distance,
        add_captured_atom_motion,
        add_initial_atom_positions,
        add_initial_line_state,
        add_interaction_distance,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_selected_pair_count,
        add_swap_conflicts,
        add_trap_support,
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
        add_initial_line_state,
        add_interaction_distance,
        add_line_order,
        add_line_speed_limit,
        add_no_motion_during_switch,
        add_selected_pair_count,
        add_swap_conflicts,
        add_trap_support,
        add_uncaptured_atom_wait,
        add_vertex_conflicts,
    )


# Operation helpers
# ========================================================================
def index_operations(cz_pairs, atom_count):
    """Assign each CZ occurrence its original index, retaining order and repeats."""
    operations = []
    for operation_id, pair in enumerate(cz_pairs):
        if len(pair) != 2:
            raise ValueError(f"Operation {operation_id} requires two atoms.")
        i, j = pair
        if (
            not isinstance(i, int)
            or not isinstance(j, int)
            or not 0 <= i < atom_count
            or not 0 <= j < atom_count
            or i == j
        ):
            raise ValueError(f"Operation {operation_id} has an invalid CZ pair: {pair}.")
        operations.append((operation_id, (min(i, j), max(i, j))))
    return operations


def get_layer_candidates(remaining_operations, preserve_gate_order):
    """Keep operations whose atoms have no pending predecessors when order is required."""
    if not preserve_gate_order:
        return list(remaining_operations)

    encountered_atoms = set()
    candidates = []
    for operation in remaining_operations:
        _, pair = operation
        if encountered_atoms.isdisjoint(pair):
            candidates.append(operation)
        # Skipped operations also block their successors on either atom.
        encountered_atoms.update(pair)
    return candidates


def main(animate=False, output_dir=None):
    """Solve the original example; edit the architecture and program parameters below."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent / "output"
    if animate:
        if __package__:
            from .visualization import animate_atom_paths
        else:
            from visualization import animate_atom_paths

    # Model parameters and enabled constraints
    # ========================================================================
    MIN_STEPS = 5
    MAX_STEPS = 10
    W, H = (5, 5)
    r_int = 1
    r_block = 3
    starts = [(0, 0), (0, 1), (0, 2), (0, 3), (2, 0)]
    slm_sites = starts + [(1, 1), (3, 2), (4, 4)]
    cz_pairs = [(0, 1), (0, 2), (0, 3), (0, 4)]
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
        "trap_support": True,
        "preserve_gate_order": True,
    }

    # Single-layer solver
    # ========================================================================
    def solve_next_layer(
        current_starts, remaining_operations, initial_rows, initial_cols, layer_index
    ):
        candidates = get_layer_candidates(
            remaining_operations, use_constraints["preserve_gate_order"]
        )
        # This set is only for geometry; operation multiplicity stays in candidates.
        candidate_pairs = {pair for _, pair in candidates}
        atom_count = len(current_starts)
        print(f"Layer {layer_index}: candidate operations (ID, pair): {candidates}")

        # Solver variables: maximize the layer size before minimizing its horizon.
        # ========================================================================
        for pair_count in range(len(candidates), 0, -1):
            for T in range(MIN_STEPS, MAX_STEPS + 1):
                atom_x = [
                    [Int(f"L{layer_index}_a{i}_x_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                atom_y = [
                    [Int(f"L{layer_index}_a{i}_y_{t}") for t in range(T + 1)]
                    for i in range(atom_count)
                ]
                r = [
                    [
                        (
                            Int(f"L{layer_index}_r_{j}_{t}"),
                            Bool(f"L{layer_index}_r_{j}_{t}_on"),
                        )
                        for j in range(r_max)
                    ]
                    for t in range(T + 1)
                ]
                c = [
                    [
                        (
                            Int(f"L{layer_index}_c_{j}_{t}"),
                            Bool(f"L{layer_index}_c_{j}_{t}_on"),
                        )
                        for j in range(c_max)
                    ]
                    for t in range(T + 1)
                ]
                chosen = {
                    operation_id: Bool(f"L{layer_index}_g{operation_id}_chosen")
                    for operation_id, pair in candidates
                }
                # A physical pair is selected if any of its occurrences is selected.
                chosen_by_pair = {
                    pair: Or(
                        [
                            chosen[operation_id]
                            for operation_id, candidate in candidates
                            if candidate == pair
                        ]
                    )
                    for pair in candidate_pairs
                }

                # Solver and constraints
                # ========================================================================
                s = Solver()
                add_selected_pair_count(s, chosen, pair_count)
                for atom in range(atom_count):
                    incident = [
                        chosen[operation_id]
                        for operation_id, pair in candidates
                        if atom in pair
                    ]
                    if len(incident) > 1:
                        s.add(PbLe([(selected, 1) for selected in incident], 1))
                if use_constraints["atom_bounds"]:
                    add_atom_bounds(s, atom_x, atom_y, W, H)
                if use_constraints["active_line_bounds"]:
                    add_active_line_bounds(s, r, c, W, H)
                if use_constraints["initial_lines_off"]:
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
                if use_constraints["interaction_distance"]:
                    add_interaction_distance(
                        s, atom_x, atom_y, candidate_pairs, r_int, chosen_by_pair
                    )
                if use_constraints["blockade_distance"]:
                    add_blockade_distance(
                        s, atom_x, atom_y, candidate_pairs, r_block, chosen_by_pair
                    )
                if use_constraints["swap_conflicts"]:
                    add_swap_conflicts(s, atom_x, atom_y)
                if use_constraints["trap_support"]:
                    add_trap_support(s, atom_x, atom_y, r, c, slm_sites)

                # Solve and interpret the model
                # ========================================================================
                result = s.check()
                if result == unsat:
                    print(f"Layer {layer_index}, K={pair_count}, T={T}: UNSAT")
                    continue
                if result == unknown:
                    raise RuntimeError(
                        f"Layer {layer_index}, K={pair_count}, T={T}: UNKNOWN ({s.reason_unknown()})"
                    )
                model = s.model()
                selected = [
                    (operation_id, pair)
                    for operation_id, pair in candidates
                    if is_true(model.eval(chosen[operation_id], model_completion=True))
                ]
                selected_ids = {operation_id for operation_id, _ in selected}
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

    # Multi-layer pipeline
    # ========================================================================
    pipeline_start = time.time()
    current_starts = list(starts)
    remaining_operations = index_operations(cz_pairs, len(starts))
    initial_rows = [(None, False) for _ in range(r_max)]
    initial_cols = [(None, False) for _ in range(c_max)]
    all_paths = [[] for _ in current_starts]
    all_rows, all_cols = ([], [])
    pulse_layers = []
    operation_layers = []
    total_steps = 0
    while remaining_operations:
        layer_index = len(pulse_layers) + 1
        layer = solve_next_layer(
            current_starts, remaining_operations, initial_rows, initial_cols, layer_index
        )
        if layer is None:
            raise RuntimeError(
                f"Could not schedule candidates within T={MIN_STEPS}..{MAX_STEPS}; "
                f"remaining operations (ID, pair): {remaining_operations}"
            )
        T, selected, deferred, paths, row_states, col_states = layer
        selected_pairs = [pair for _, pair in selected]
        selected_ids = [operation_id for operation_id, _ in selected]
        print(f"Layer {layer_index}: T={T}, selected operations (ID, pair): {selected}")
        print(f"Deferred operations (ID, pair): {deferred}")
        # Adjacent layers share their boundary atom and AOD state.
        first_frame = 0 if layer_index == 1 else 1
        for i, path in enumerate(paths):
            all_paths[i].extend(path[first_frame:])
        all_rows.extend(
            [
                [position for position, on in state if on]
                for state in row_states[first_frame:]
            ]
        )
        all_cols.extend(
            [
                [position for position, on in state if on]
                for state in col_states[first_frame:]
            ]
        )
        total_steps += T
        pulse_layers.append((total_steps, selected_pairs))
        operation_layers.append((total_steps, selected_ids))
        current_starts = [path[-1] for path in paths]
        initial_rows = row_states[-1]
        initial_cols = col_states[-1]
        remaining_operations = deferred
        print(
            f"Atom positions after the layer: {current_starts}; global step: {total_steps}"
        )
    # Visualization and output
    # ========================================================================
    print(f"All CZ operations completed. Layers: {len(pulse_layers)}; steps: {total_steps}.")
    print(f"Rydberg layers (global step, CZ pairs): {pulse_layers}")
    print(f"Executed operations (global step, IDs): {operation_layers}")
    print(f"Execution time: {round(time.time() - pipeline_start)} s")
    if all_paths and all_paths[0]:
        if animate:
            animate_atom_paths(
                [[0] * W for _ in range(H)],
                all_paths,
                marked_cells=slm_sites,
                rows=all_rows,
                columns=all_cols,
                rydberg_layers=pulse_layers,
                fps=2,
                output_path=str(Path(output_dir) / "scheduled_cz_layers.mp4"),
            )
    return {
        "paths": all_paths,
        "rows": all_rows,
        "columns": all_cols,
        "layers": pulse_layers,
        "operation_layers": operation_layers,
        "total_steps": total_steps,
    }


if __name__ == "__main__":
    # Command-line interface
    # ========================================================================
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Save a figure or MP4; MP4 needs ffmpeg.",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Directory for optional figures and animations."
    )
    parser.add_argument("--json", type=Path, help="Write the solved schedule as JSON.")
    args = parser.parse_args()
    result = main(animate=args.animate, output_dir=args.output_dir)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n")
