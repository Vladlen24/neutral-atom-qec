# External compiler experiments

Experiments with existing neutral-atom compilation tools, using shared
quantum error-correction circuit definitions.

| Notebook | Compilation method |
| --- | --- |
| [`mqt_compiler_zonedNAarch.ipynb`](mqt_compiler_zonedNAarch.ipynb) | MQT QMAP routing-aware compilation for zoned architectures |
| [`hyrona.ipynb`](hyrona.ipynb) | HyRoNA hybrid gate-based and atom-shuttling routing |
| [`DPQA_compiler.ipynb`](DPQA_compiler.ipynb) | OLSQ-DPQA CZ routing with a separate extended checkout |

## Setup

```sh
python3 -m pip install -r requirements-experiments.txt
```

Open the notebooks from the repository root. Visualization files are exported
to `visualisation_instructions/`; MP4 generation additionally requires `ffmpeg`.

## Source circuits and native gates

[`circuit.py`](circuit.py) defines rotated-surface-code and Steane-code
preparations, graph-state preparations, verified preparations, and a
hand-scheduled 17-qubit surface-code circuit. Circuit synthesis uses
[MQT QECC](https://github.com/munich-quantum-toolkit/qecc); its
[citation guidance](https://github.com/munich-quantum-toolkit/qecc#cite-this)
lists the corresponding synthesis methods.

[`transpiler.py`](transpiler.py) lowers unitary operations to global RY, local
RZ, and CZ gates for the zoned compiler. It removes barriers and measurements,
decomposes CX into H-CZ-H, and optionally simplifies native rotations.
HyRoNA receives the source circuit directly.

## MQT QMAP and HyRoNA

Both experiments use [MQT QMAP](https://github.com/munich-quantum-toolkit/qmap)
and export inputs for [MQT NAViz](https://github.com/munich-quantum-toolkit/naviz).
The method descriptions and references are available in the
[zoned compiler documentation](https://mqt.readthedocs.io/projects/qmap/en/stable/na_zoned_compiler.html),
[HyRoNA documentation](https://mqt.readthedocs.io/projects/qmap/en/stable/na_hybrid.html),
and [QMAP citation guidance](https://github.com/munich-quantum-toolkit/qmap#cite-this).

## OLSQ-DPQA dependency

The DPQA notebook requires a separate extended
[OLSQ-DPQA](https://github.com/UCLA-VAST/DPQA) checkout at
`dpqa_compiler/DPQA/`. The external source and extensions are not included here.
The notebook expects upstream revision `600df66af4136ccdab88b49c28e1771ef2a8cbe9`
with a `single_qubit.py` helper, command-line options for circuit-operation JSON
and architecture settings, and single-qubit instruction/animation support.
An unmodified upstream checkout does not provide this interface.

DPQA routes CZ gates; inserted single-qubit layers preserve source order but
do not optimize their calibrated timing or addressability. The example has
Hadamards between CZ blocks, so global CZ commutation is not enabled.

The [main branch](https://github.com/Vladlen24/neutral-atom-qec)
contains the SMT compiler.
