"""Transpilation to the native neutral-atom basis used by this project."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import CircuitInstruction, Gate


_NATIVE_GATES = {"cz", "global_ry", "rz"}
_SUPPORTED_SOURCE_GATES = {"cx", "cz", "h", "id", "rz", "s", "sdg", "x", "y", "z"}


def _qubit_indices(circuit: QuantumCircuit, instruction: CircuitInstruction) -> tuple[int, ...]:
    return tuple(circuit.find_bit(qubit).index for qubit in instruction.qubits)


def _copy_from_records(
    num_qubits: int,
    records: Iterable[tuple[Gate, tuple[int, ...]]],
) -> QuantumCircuit:
    out = QuantumCircuit(num_qubits)
    for operation, qubits in records:
        out.append(operation, qubits)
    return out


def _strip_barriers_and_measurements(circuit: QuantumCircuit) -> QuantumCircuit:
    """Remove non-unitary operations that are irrelevant to compilation."""
    records = [
        (instruction.operation, _qubit_indices(circuit, instruction))
        for instruction in circuit.data
        if instruction.operation.name not in {"barrier", "measure"}
    ]
    return _copy_from_records(circuit.num_qubits, records)


def _cancel_h_gates(circuit: QuantumCircuit) -> QuantumCircuit:
    """Cancel H pairs that are consecutive on their qubit."""
    records: list[tuple[Gate, tuple[int, ...]]] = []

    for instruction in circuit.data:
        operation = instruction.operation
        qubits = _qubit_indices(circuit, instruction)

        if operation.name == "h":
            qubit = qubits[0]
            for index in range(len(records) - 1, -1, -1):
                previous_operation, previous_qubits = records[index]
                if qubit not in previous_qubits:
                    continue
                if previous_operation.name == "h" and previous_qubits == qubits:
                    records.pop(index)
                    break
                records.append((operation, qubits))
                break
            else:
                records.append((operation, qubits))
        else:
            records.append((operation, qubits))

    return _copy_from_records(circuit.num_qubits, records)


def to_cz_h_basis(circuit: QuantumCircuit) -> QuantumCircuit:
    """Replace every CX by H-CZ-H and remove redundant H pairs."""
    source = _strip_barriers_and_measurements(circuit)
    out = QuantumCircuit(source.num_qubits)

    for instruction in source.data:
        operation = instruction.operation
        qubits = _qubit_indices(source, instruction)
        name = operation.name

        if name not in _SUPPORTED_SOURCE_GATES:
            raise ValueError(f"Unsupported source gate: {name}")
        if name == "id":
            continue
        if name == "cx":
            control, target = qubits
            out.h(target)
            out.cz(control, target)
            out.h(target)
        else:
            out.append(operation, qubits)

    return _cancel_h_gates(out)


def _global_ry(theta: float, num_qubits: int) -> Gate:
    definition = QuantumCircuit(num_qubits, name="global_ry")
    definition.ry(theta, range(num_qubits))
    return definition.to_gate(label=f"global RY({theta:.3f})")


def _append_native_h(circuit: QuantumCircuit, qubit: int) -> None:
    num_qubits = circuit.num_qubits
    circuit.append(_global_ry(-np.pi / 4, num_qubits), range(num_qubits))
    circuit.rz(np.pi, qubit)
    circuit.append(_global_ry(np.pi / 4, num_qubits), range(num_qubits))


def _lower_single_qubit_gates(circuit: QuantumCircuit) -> QuantumCircuit:
    out = QuantumCircuit(circuit.num_qubits)

    for instruction in circuit.data:
        operation = instruction.operation
        qubits = _qubit_indices(circuit, instruction)
        name = operation.name

        if name == "cz":
            out.cz(*qubits)
        elif name == "h":
            _append_native_h(out, qubits[0])
        elif name == "rz":
            out.rz(float(operation.params[0]), qubits[0])
        elif name == "s":
            out.rz(np.pi / 2, qubits[0])
        elif name == "sdg":
            out.rz(-np.pi / 2, qubits[0])
        elif name == "z":
            out.rz(np.pi, qubits[0])
        elif name == "x":
            _append_native_h(out, qubits[0])
            out.rz(np.pi, qubits[0])
            _append_native_h(out, qubits[0])
        elif name == "y":
            _append_native_h(out, qubits[0])
            out.rz(np.pi, qubits[0])
            _append_native_h(out, qubits[0])
            out.rz(np.pi, qubits[0])
        else:
            raise ValueError(f"Cannot lower gate to the native basis: {name}")

    return out


def _global_ry_angle(operation: Gate, num_qubits: int) -> float | None:
    if operation.name != "global_ry" or operation.definition is None or operation.num_qubits != num_qubits:
        return None
    gates = operation.definition.data
    if len(gates) != num_qubits or any(gate.operation.name != "ry" for gate in gates):
        return None
    angles = [float(gate.operation.params[0]) for gate in gates]
    return angles[0] if all(np.isclose(angle, angles[0]) for angle in angles) else None


def _is_zero_angle(theta: float, atol: float) -> bool:
    return bool(np.isclose(theta % (2 * np.pi), 0, atol=atol))


def _optimize_native_once(circuit: QuantumCircuit, atol: float) -> tuple[QuantumCircuit, bool]:
    records: list[tuple[Gate, tuple[int, ...]]] = []
    changed = False

    for instruction in circuit.data:
        operation = instruction.operation
        qubits = _qubit_indices(circuit, instruction)
        global_angle = _global_ry_angle(operation, circuit.num_qubits)

        if global_angle is not None:
            if records:
                previous_operation, _ = records[-1]
                previous_angle = _global_ry_angle(previous_operation, circuit.num_qubits)
                if previous_angle is not None:
                    records.pop()
                    total = previous_angle + global_angle
                    if not _is_zero_angle(total, atol):
                        records.append((_global_ry(total, circuit.num_qubits), tuple(range(circuit.num_qubits))))
                    changed = True
                    continue
            if _is_zero_angle(global_angle, atol):
                changed = True
                continue
            records.append((operation, qubits))
            continue

        if operation.name == "rz":
            qubit = qubits[0]
            angle = float(operation.params[0])
            for index in range(len(records) - 1, -1, -1):
                previous_operation, previous_qubits = records[index]
                if qubit not in previous_qubits:
                    continue
                if previous_operation.name == "rz" and previous_qubits == qubits:
                    records.pop(index)
                    angle += float(previous_operation.params[0])
                    changed = True
                break
            if _is_zero_angle(angle, atol):
                changed = True
                continue
            normalized_angle = (angle + np.pi) % (2 * np.pi) - np.pi
            if not np.isclose(normalized_angle, angle, atol=atol):
                changed = True
            normalized = QuantumCircuit(1)
            normalized.rz(normalized_angle, 0)
            records.append((normalized.data[0].operation, qubits))
            continue

        if operation.name == "cz":
            endpoints = frozenset(qubits)
            for index in range(len(records) - 1, -1, -1):
                previous_operation, previous_qubits = records[index]
                if endpoints.isdisjoint(previous_qubits):
                    continue
                if previous_operation.name == "cz" and frozenset(previous_qubits) == endpoints:
                    records.pop(index)
                    changed = True
                else:
                    records.append((operation, qubits))
                break
            else:
                records.append((operation, qubits))
            continue

        records.append((operation, qubits))

    return _copy_from_records(circuit.num_qubits, records), changed


def _optimize_native(circuit: QuantumCircuit, atol: float = 1e-9) -> QuantumCircuit:
    while True:
        circuit, changed = _optimize_native_once(circuit, atol)
        if not changed:
            return circuit


def _validate_native(circuit: QuantumCircuit) -> None:
    unexpected = sorted({instruction.operation.name for instruction in circuit.data} - _NATIVE_GATES)
    if unexpected:
        raise ValueError(f"Non-native gates remain after transpilation: {unexpected}")


def transpile_to_native(
    circuit: QuantumCircuit,
    *,
    optimize: bool = True,
) -> QuantumCircuit:
    """Transpile to global RY, local RZ, and CZ gates."""
    cz_h_circuit = to_cz_h_basis(circuit)
    native_circuit = _lower_single_qubit_gates(cz_h_circuit)
    if optimize:
        native_circuit = _optimize_native(native_circuit)
    _validate_native(native_circuit)
    return native_circuit


__all__ = ["to_cz_h_basis", "transpile_to_native"]
