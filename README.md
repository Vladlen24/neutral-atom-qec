# Neutral-Atom Quantum Compilation Experiments

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
