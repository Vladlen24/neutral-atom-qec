"""17-qubit distance-3 surface-code example in the placement input format.

Source: build_17_qubit_surface_code_circuit in circuit.py, external_compilers
branch, commit 1c2fec30570c9060572d1015014b855dff14e2b1. This input uses no
external circuit-synthesis library. Source barriers are scheduling annotations;
the placement pipeline preserves per-atom gate order.
"""

from math import pi


# Source qubit numbering and gate blocks
# ========================================================================
QUBIT_NAMES = (
    "x1",
    "d1",
    "d2",
    "d3",
    "z1",
    "x2",
    "z3",
    "d4",
    "d5",
    "d6",
    "z2",
    "x3",
    "z4",
    "d7",
    "d8",
    "d9",
    "x4",
)
DATA_QUBITS = tuple(f"d{i}" for i in range(1, 10))
OUTER_H = (
    "x1",
    "d1",
    "d3",
    "z1",
    "x2",
    "z3",
    "d5",
    "z2",
    "x3",
    "z4",
    "d7",
    "d9",
    "x4",
)
SOURCE_BLOCKS = (
    ("h", OUTER_H),
    (
        "cz",
        (
            ("d2", "z3"),
            ("d3", "x2"),
            ("d4", "z4"),
            ("d5", "x3"),
            ("d6", "z2"),
            ("d9", "x4"),
        ),
    ),
    ("h", DATA_QUBITS),
    (
        "cz",
        (
            ("d2", "x2"),
            ("z3", "d5"),
            ("z2", "d9"),
            ("d4", "x3"),
            ("z4", "d7"),
            ("d8", "x4"),
        ),
    ),
    (
        "cz",
        (
            ("x1", "d2"),
            ("d3", "z1"),
            ("x2", "d6"),
            ("x3", "d8"),
            ("d1", "z3"),
            ("d5", "z2"),
        ),
    ),
    ("h", DATA_QUBITS),
    (
        "cz",
        (
            ("x1", "d1"),
            ("z1", "d6"),
            ("z2", "d8"),
            ("x2", "d5"),
            ("x3", "d7"),
            ("z3", "d4"),
        ),
    ),
    ("h", OUTER_H),
)


# Lower each H block to global RY and local RZ rotations
# ========================================================================
def build_gate_seq():
    """Return the full circuit, equivalent up to a global phase.

    For any target set Q, applying global RY(-pi/4), RZ(pi) on Q,
    then global RY(pi/4) implements H on Q up to phase. Non-target
    atoms receive opposite global rotations and therefore the identity.
    """
    index = {name: atom for atom, name in enumerate(QUBIT_NAMES)}
    gates = []
    for kind, block in SOURCE_BLOCKS:
        if kind == "h":
            gates.append(("global", ("ry", -pi / 4)))
            gates.extend((index[name], ("rz", pi)) for name in block)
            gates.append(("global", ("ry", pi / 4)))
        else:
            gates.extend((index[first], index[second]) for first, second in block)
    return gates


# Arbitrary initial placement on a regular array of SLM pairs
# ========================================================================
ATOM_ROLES = ["data" if name.startswith("d") else "ancilla" for name in QUBIT_NAMES]
ARCHITECTURE = {
    "width": 14,
    "height": 13,
    "slm_sites": [
        (4 * col + offset, 3 * row)
        for row in range(5)
        for col in range(4)
        for offset in (0, 1)
    ],
    "starts": [(4 * (atom % 4), 3 * (atom // 4)) for atom in range(len(QUBIT_NAMES))],
    "r_int": 1,
    "r_block": 3,
    "r_crosstalk": 2,
}
