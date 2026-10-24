"""Reusable source-circuit definitions for external compilation experiments.

Code construction and state-preparation synthesis use MQT QECC:
https://github.com/munich-quantum-toolkit/qecc
"""

import numpy as np
from qiskit import QuantumCircuit

from mqt.qecc.circuit_synthesis import (
    CNOTCircuit,
    FaultyStatePrepCircuit,
    gate_optimal_prep_circuit,
    gate_optimal_verification_circuit,
)
from mqt.qecc.codes import CSSCode, RotatedSurfaceCode


def _build_verified_zero_state(
    code: CSSCode,
    *,
    max_ancillas: int | None,
    min_prep_gates: int,
    max_prep_gates: int,
    min_timeout: int,
    max_timeout: int,
) -> QuantumCircuit:
    state_prep = gate_optimal_prep_circuit(
        code,
        zero_state=True,
        min_gates=min_prep_gates,
        max_gates=max_prep_gates,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )
    if state_prep is None:
        raise RuntimeError("Could not synthesize the state-preparation circuit.")

    return gate_optimal_verification_circuit(
        state_prep,
        max_ancillas=max_ancillas,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )


def build_rotated_surface_code_circuit(
    distance: int = 3,
    *,
    max_ancillas: int | None = 2,
    min_prep_gates: int = 1,
    max_prep_gates: int = 15,
    min_timeout: int = 1,
    max_timeout: int = 60,
) -> QuantumCircuit:
    """Build a verified logical-zero preparation for a rotated surface code."""
    code = RotatedSurfaceCode(distance=distance)
    return _build_verified_zero_state(
        code,
        max_ancillas=max_ancillas,
        min_prep_gates=min_prep_gates,
        max_prep_gates=max_prep_gates,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )


def build_steane_code_circuit(
    *,
    max_ancillas: int | None = 2,
    min_prep_gates: int = 1,
    max_prep_gates: int = 15,
    min_timeout: int = 1,
    max_timeout: int = 60,
) -> QuantumCircuit:
    """Build a verified logical-zero preparation for the [[7, 1, 3]] Steane code."""
    code = CSSCode.from_code_name("Steane")
    return _build_verified_zero_state(
        code,
        max_ancillas=max_ancillas,
        min_prep_gates=min_prep_gates,
        max_prep_gates=max_prep_gates,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )


def _graph_form(code: CSSCode) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Return the bipartite graph representation of a CSS logical zero."""
    hx = np.asarray(code.Hx, dtype=np.uint8) % 2
    row = 0
    left: list[int] = []

    for column in range(hx.shape[1]):
        candidates = np.flatnonzero(hx[row:, column])
        if candidates.size == 0:
            continue

        pivot = row + int(candidates[0])
        hx[[row, pivot]] = hx[[pivot, row]]
        for other_row in range(hx.shape[0]):
            if other_row != row and hx[other_row, column]:
                hx[other_row] ^= hx[row]

        left.append(column)
        row += 1
        if row == hx.shape[0]:
            break

    if row != hx.shape[0]:
        raise ValueError("The X-stabilizer generators must be independent.")

    right = [qubit for qubit in range(code.n) if qubit not in left]
    adjacency = hx[:, right]
    edges = [(left[i], right[j]) for i, j in np.argwhere(adjacency)]
    return edges, left, right


def build_rotated_surface_code_graph_state_circuit(distance: int = 3) -> QuantumCircuit:
    """Build the graph state underlying rotated-surface-code |0_L> preparation."""
    code = RotatedSurfaceCode(distance=distance)
    edges, _, _ = _graph_form(code)
    circuit = QuantumCircuit(code.n, name=f"surface_code_d{distance}_graph_state")
    circuit.h(range(code.n))
    for q0, q1 in edges:
        circuit.cz(q0, q1)
    return circuit


def _as_cz_blocks(
    reference: QuantumCircuit,
    graph_edges: list[tuple[int, int]],
    right: list[int],
    n_data: int,
) -> QuantumCircuit:
    """Rebuild a verified graph-state preparation as homogeneous CZ blocks."""
    z_edges: list[tuple[int, int]] = []
    x_edges: list[tuple[int, int]] = []
    measurement_bits: dict[int, int] = {}

    for instruction in reference.data:
        operation = instruction.operation
        qubits = [reference.find_bit(qubit).index for qubit in instruction.qubits]

        if operation.name == "measure":
            measurement_bits[qubits[0]] = reference.find_bit(instruction.clbits[0]).index
        elif operation.num_qubits == 2 and any(qubit >= n_data for qubit in qubits):
            if operation.name != "cx":
                raise ValueError(f"Unsupported verification gate: {operation.name}")
            control, target = qubits
            if control < n_data <= target:
                z_edges.append((control, target))
            elif target < n_data <= control:
                x_edges.append((control, target))
            else:
                raise ValueError(f"Unsupported ancilla-ancilla CX: {qubits}")

    z_ancillas = sorted({ancilla for _, ancilla in z_edges})
    x_ancillas = sorted({ancilla for ancilla, _ in x_edges})
    x_data = sorted({data for _, data in x_edges})

    out = QuantumCircuit(*reference.qregs, *reference.cregs)

    def append_h_layer(qubits: list[int]) -> None:
        if qubits:
            out.h(qubits)

    out.h(range(n_data))
    out.barrier(label="initial H")
    for qubits in graph_edges:
        out.cz(*qubits)
    out.barrier(label="graph CZ")

    append_h_layer(sorted(set(right) | set(z_ancillas)))
    out.barrier(label="CSS / Z basis H")
    for qubits in z_edges:
        out.cz(*qubits)
    out.barrier(label="Z verification CZ")

    append_h_layer(sorted(set(z_ancillas) | set(x_ancillas) | set(x_data)))
    for ancilla in z_ancillas:
        out.measure(ancilla, measurement_bits[ancilla])
    out.barrier(label="Z measure / X basis H")

    for qubits in x_edges:
        out.cz(*qubits)
    out.barrier(label="X verification CZ")

    append_h_layer(sorted(set(x_ancillas) | set(x_data)))
    for ancilla in x_ancillas:
        out.measure(ancilla, measurement_bits[ancilla])
    return out


def _build_blockwise_cz_verification(
    code: CSSCode,
    *,
    max_ancillas: int | None,
    min_timeout: int,
    max_timeout: int,
) -> QuantumCircuit:
    graph_edges, left, right = _graph_form(code)
    graph_prep = CNOTCircuit.from_cnot_list(
        graph_edges,
        initialize_x=left,
        initialize_z=right,
    )
    faulty_prep = FaultyStatePrepCircuit(
        graph_prep,
        max_x_errors=code.x_distance // 2,
        max_z_errors=code.z_distance // 2,
    )
    verified_prep = gate_optimal_verification_circuit(
        faulty_prep,
        max_ancillas=max_ancillas,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )
    return _as_cz_blocks(verified_prep, graph_edges, right, code.n)


def build_blockwise_cz_verification_circuit(
    distance: int = 3,
    *,
    max_ancillas: int | None = 2,
    min_timeout: int = 1,
    max_timeout: int = 60,
) -> QuantumCircuit:
    """Build rotated-surface-code preparation and verification as CZ blocks."""
    return _build_blockwise_cz_verification(
        RotatedSurfaceCode(distance=distance),
        max_ancillas=max_ancillas,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )


def build_steane_blockwise_cz_verification_circuit(
    *,
    max_ancillas: int | None = 2,
    min_timeout: int = 1,
    max_timeout: int = 60,
) -> QuantumCircuit:
    """Build Steane-code preparation and verification as separate CZ blocks."""
    return _build_blockwise_cz_verification(
        CSSCode.from_code_name("Steane"),
        max_ancillas=max_ancillas,
        min_timeout=min_timeout,
        max_timeout=max_timeout,
    )


def build_17_qubit_surface_code_circuit() -> QuantumCircuit:
    """Build the hand-scheduled 9-data/8-ancilla surface-code circuit."""
    names = (
        "x1", "d1", "d2", "d3", "z1", "x2", "z3", "d4", "d5",
        "d6", "z2", "x3", "z4", "d7", "d8", "d9", "x4",
    )
    qubit = {name: index for index, name in enumerate(names)}
    data = tuple(f"d{i}" for i in range(1, 10))
    outer_h_layer = (
        "x1", "d1", "d3", "z1", "x2", "z3", "d5",
        "z2", "x3", "z4", "d7", "d9", "x4",
    )
    circuit = QuantumCircuit(len(names), name="surface_code_17")

    def h_layer(layer: tuple[str, ...]) -> None:
        circuit.h([qubit[name] for name in layer])
        circuit.barrier()

    def cz_layer(*pairs: tuple[str, str]) -> None:
        for first, second in pairs:
            circuit.cz(qubit[first], qubit[second])
        circuit.barrier()

    h_layer(outer_h_layer)
    cz_layer(
        ("d2", "z3"),
        ("d3", "x2"),
        ("d4", "z4"),
        ("d5", "x3"),
        ("d6", "z2"),
        ("d9", "x4"),
    )
    h_layer(data)
    cz_layer(
        ("d2", "x2"),
        ("z3", "d5"),
        ("z2", "d9"),
        ("d4", "x3"),
        ("z4", "d7"),
        ("d8", "x4"),
    )
    cz_layer(
        ("x1", "d2"),
        ("d3", "z1"),
        ("x2", "d6"),
        ("x3", "d8"),
        ("d1", "z3"),
        ("d5", "z2"),
    )
    h_layer(data)
    cz_layer(
        ("x1", "d1"),
        ("z1", "d6"),
        ("z2", "d8"),
        ("x2", "d5"),
        ("x3", "d7"),
        ("z3", "d4"),
    )

    circuit.h([qubit[name] for name in outer_h_layer])
    return circuit


__all__ = [
    "build_17_qubit_surface_code_circuit",
    "build_blockwise_cz_verification_circuit",
    "build_rotated_surface_code_circuit",
    "build_steane_blockwise_cz_verification_circuit",
    "build_steane_code_circuit",
]
