# Neutral-Atom Quantum Compilation Experiments

## Independent SMT compiler

The main research direction is an independently implemented Z3 prototype
for a universal neutral-atom quantum compiler. Its current scope is discrete
atom transport and successive layers of unique, mutually commuting CZ gates
under a global Rydberg pulse. Each layer first maximizes the number of CZ
pairs, then minimizes the feasible logical horizon in the configured range.

- [`solver/compiler.py`](solver/compiler.py): the evolving compiler script.
- [`solver/constraints.py`](solver/constraints.py): reusable SMT constraints.
- [`solver/README.md`](solver/README.md): LaTeX formulas, assumptions, usage,
  development commits, and validation.
- [`solver/smt_introduction.py`](solver/smt_introduction.py): the initial
  Sudoku-style, graph-coloring, and maze experiments in one introductory step.

```sh
python3 -m pip install -r solver/requirements.txt
python3 solver/compiler.py
python3 -m unittest discover -s solver -p "test_*.py"
```

The SMT implementation uses Z3 and optional Matplotlib visualization. It is
independent of the external compilers explored below. The long working
notebook and Russian deferred questions remain local development material.

[![SMT scheduling demo](solver/media/scheduled_cz_layers.png)](solver/media/scheduled_cz_layers.mp4)

The local branch `organize-research-history` contains the manual compilation
and external experiments. `smt-compiler` continues that branch with the
independent SMT development sequence.

## Manual compilation

[`main.ipynb`](main.ipynb) is an interactive editor for hand-scheduled atom
transport and gate highlights. It uses two families of diagonal AOD frequency
lines. Choose a configuration, edit the iteration program, and inspect the
resulting atom movements.

Open the notebook in a Jupyter environment with `IPython` installed and run
the main code cell. Load
[`settings/atom_grid_config_v2.0_fix.json`](settings/atom_grid_config_v2.0_fix.json)
using the editor's JSON controls to inspect the corrected demonstration.

[![Manual compilation demo](media/visualization.png)](media/atom_configuration_v2.0_fix.mp4)

- [Corrected demonstration](media/atom_configuration_v2.0_fix.mp4)
- [Earlier demonstration](media/atom_config_v2.0.mp4) and its
  [configuration](settings/atom_grid_config_v2.0.json)

The saved HTML output in the notebook is refreshed together with the corrected
configuration and video; the editor's source code is unchanged in this update.

Local research drafts, reference documents, generated files, and independent
external checkouts are excluded from version control.

## External compiler experiments

These experiments explore existing compilation tools. Their shared input
circuits are defined in [`circuit.py`](circuit.py): rotated-surface-code and
Steane-code preparations, graph-state preparations, verified preparations,
and a hand-scheduled 17-qubit surface-code circuit.

Circuit synthesis uses [MQT QECC](https://github.com/munich-quantum-toolkit/qecc).
See its [citation guidance](https://github.com/munich-quantum-toolkit/qecc#cite-this)
for the corresponding state-preparation and verification methods.

Install the experiment dependencies in a separate Python environment:

```sh
python3 -m pip install -r requirements-experiments.txt
```

The original notebook environments were not recorded. The requirements list
the imported packages; it is not a lockfile for those historical environments.

[`transpiler.py`](transpiler.py) lowers unitary circuit operations to global
RY rotations, local RZ rotations, and local CZ gates for the zoned-architecture
experiment. It removes barriers and measurements, rewrites CX as H-CZ-H,
and optionally cancels compatible native rotations. Measurement semantics
are outside this transpilation experiment.

### MQT QMAP: zoned architectures

[`mqt_compiler_zonedNAarch.ipynb`](mqt_compiler_zonedNAarch.ipynb) selects a
shared source circuit, lowers it to the native gate set, defines storage and
entanglement zones, and runs the routing-aware compiler. It exports `.naviz`
and `.namachine` files into the ignored `visualisation_instructions/` folder.
Open the notebook from the repository root with its dependencies installed.

This experiment uses [MQT QMAP](https://github.com/munich-quantum-toolkit/qmap)
and exports programs for [MQT NAViz](https://github.com/munich-quantum-toolkit/naviz).
The [zoned compiler documentation](https://mqt.readthedocs.io/projects/qmap/en/stable/na_zoned_compiler.html)
describes the routing-aware and routing-agnostic methods and their references.
See also [QMAP's citation guidance](https://github.com/munich-quantum-toolkit/qmap#cite-this).

### MQT QMAP: HyRoNA

[`hyrona.ipynb`](hyrona.ipynb) maps a source circuit using HyRoNA's hybrid
gate-based and atom-shuttling strategies, schedules the result, and exports
NAViz inputs. The source circuit is passed directly to the mapper; this
experiment does not use the separate zoned native-basis transpiler.

HyRoNA is part of [MQT QMAP](https://github.com/munich-quantum-toolkit/qmap).
See the [hybrid mapper documentation](https://mqt.readthedocs.io/projects/qmap/en/stable/na_hybrid.html)
and QMAP's references for the underlying routing method.

### OLSQ-DPQA

[`DPQA_compiler.ipynb`](DPQA_compiler.ipynb) is an experiment with the external
[OLSQ-DPQA compiler](https://github.com/UCLA-VAST/DPQA). It extracts CZ
interactions from a Qiskit source circuit and invokes a separate local checkout
at `dpqa_compiler/DPQA/`. That checkout is ignored by Git and is not distributed
with this repository. The SMT compiler developed in `solver/` has its own
implementation and does not import or invoke DPQA.

The experiment used upstream revision
`600df66af4136ccdab88b49c28e1771ef2a8cbe9` with additional local extensions:
`single_qubit.py`, command-line options for circuit-operation JSON and explicit
architecture settings, and instruction/animation handling for inserted
single-qubit layers. Those extensions are not published here. An unmodified
upstream checkout is insufficient to run this notebook; the notebook is a
record of the locally extended experiment. Its original solver and animation
environment remains separate from the Qiskit environment.

DPQA routes CZ gates; the inserted single-qubit layers preserve source order
but do not optimize calibrated hardware timing or addressability. The example
includes Hadamards between CZ blocks, so global CZ commutation is not enabled.
For the external compiler and the corresponding publications, consult the
[upstream README](https://github.com/UCLA-VAST/DPQA#readme).
