# SMT-based neutral-atom compiler development

This directory contains an independently implemented Z3 research prototype
for neutral-atom transport and CZ-layer scheduling. It does not import,
invoke, or distribute OLSQ-DPQA or MQT compiler code. Those tools belong to
the separate experiments described in the root README.

The Python implementation is reconstructed from the original development
steps. The working research notebook and Russian questions remain local.
Successive commits extend the same `compiler.py`; this README changes with
the formulas available at each step.

## Setup and introductory examples

```sh
python3 -m pip install -r solver/requirements.txt
python3 solver/smt_introduction.py
```

The examples need Z3. Matplotlib is used only for optional transport figures
and animations; MP4 export additionally needs an installed `ffmpeg` executable.

### Sudoku-style row and column constraints

The original 4-by-4 example is a Latin-square relaxation of Sudoku: it has
row and column uniqueness but no 2-by-2 subgrid constraints. This historical
formulation is intentionally retained.

$$
1\le X_{ij}\le4,\quad
\operatorname{Distinct}(X_{i0},\ldots,X_{i3}),\quad
\operatorname{Distinct}(X_{0j},\ldots,X_{3j}),
$$

$$X_{00}=1,\qquad X_{12}=3.$$

### Graph coloring

For the adjacency matrix in `smt_introduction.py`, assign one of three colors
to each vertex; adjacent vertices must differ:

$$1\le c_i\le3,\qquad (i,j)\in E\Rightarrow c_i\ne c_j.$$

### Maze path finding

For an increasing number of path cells $n$, constrain $p_0=s$, $p_{n-1}=g$,
require all cells to be in bounds and outside the wall set $B$, and forbid
repeated cells. Consecutive cells are cardinal neighbors:

$$
p_k\in G\setminus B,\quad
\|p_{k+1}-p_k\|_1=1,\quad
k\ne m\Rightarrow p_k\ne p_m.
$$

These are standalone SMT learning examples, separate from the physical
assumptions of the transport model below.

## Running the current compiler stage

```sh
python3 solver/compiler.py
python3 solver/compiler.py --animate
```

Edit the example parameters at the start of `main()` in `compiler.py` to
reproduce a different instance. The default run solves and prints a schedule;
`--animate` additionally writes figures or MP4 files under `solver/output/`.
Use `--output-dir PATH` to choose another location. Generated output is not
versioned. Every historical stage is a runnable snapshot.

## Notation

Atoms are indexed by $i$, and logical states by $t=0,\ldots,T$.
The integer position is $p_i^t=(x_i^t,y_i^t)$ on
$G=\{0,\ldots,W-1\}\times\{0,\ldots,H-1\}$.
The horizon $T$ counts logical transitions, not calibrated hardware time.
Atom identities are fixed; this is a transport/scheduling prototype rather
than a full quantum-circuit frontend.

## Current constraint system

Current stage: **Extract reusable SMT constraint functions**.

### C01. Atom bounds and initial positions

$$\forall i,t:\quad 0\le x_i^t<W,\quad0\le y_i^t<H,\qquad p_i^0=s_i.$$

### C04. Vertex and swap conflicts

$$\forall i<j,t:\quad p_i^t\ne p_j^t.$$

$$\forall i<j,t<T:\quad
\neg(p_i^t=p_j^{t+1}\land p_j^t=p_i^{t+1}).$$

These are discrete vertex/swap constraints. They do not prove collision
avoidance along every continuous trajectory between sampled states.

### C05. AOD line states and domains

For AOD row $j$, $R_j^t$ is its enabled state and $\rho_j^t$ its integer
$y$ coordinate. For column $k$, $C_k^t$ and $\gamma_k^t$ give its enabled
state and integer $x$ coordinate. Coordinates of inactive lines are free.

$$R_j^t\Rightarrow0\le\rho_j^t<H,\qquad
C_k^t\Rightarrow0\le\gamma_k^t<W.$$

Initially all lines are disabled:

$$\forall j,k:\quad\neg R_j^0\land\neg C_k^0.$$

### C06. Speed of continuously active lines

$$R_j^t\land R_j^{t+1}\Rightarrow
|\rho_j^{t+1}-\rho_j^t|\le1,$$

$$C_k^t\land C_k^{t+1}\Rightarrow
|\gamma_k^{t+1}-\gamma_k^t|\le1.$$

This is a discrete displacement bound, not a calibrated capture or velocity
model. A line can be activated at an otherwise unconstrained in-bounds position.

### C07. Separate switching from motion

Define whether any row or column changes its enabled state:

$$S_t=\left(\bigvee_j R_j^t\ne R_j^{t+1}\right)
\lor\left(\bigvee_k C_k^t\ne C_k^{t+1}\right).$$

When $S_t$ holds, every continuously active line keeps its coordinate:

$$S_t\land R_j^t\land R_j^{t+1}\Rightarrow\rho_j^{t+1}=\rho_j^t,$$

$$S_t\land C_k^t\land C_k^{t+1}\Rightarrow\gamma_k^{t+1}=\gamma_k^t.$$

### C08. Coordinate-based capture and coupled atom motion

An atom is captured by intersection $(j,k)$ when

$$B_{ijk}^t=R_j^t\land C_k^t\land y_i^t=\rho_j^t\land x_i^t=\gamma_k^t.$$

For every capturing intersection, provided no line switches:

$$\neg S_t\land B_{ijk}^t\Rightarrow
(x_i^{t+1}=\gamma_k^{t+1}\land y_i^{t+1}=\rho_j^{t+1}).$$

During switching, or without a capturing intersection, the atom waits:

$$\left(S_t\lor\neg\bigvee_{j,k}B_{ijk}^t\right)
\Rightarrow p_i^{t+1}=p_i^t.$$

Capture is automatic at a coincident active intersection. An explicit
SLM-to-AOD transfer state, physical capture duration, and accidental-capture
conditions are not modeled.

### C09. Preserve the order of continuously active lines

For rows, define $A_{jm}^t=R_j^t\land R_m^t\land R_j^{t+1}\land R_m^{t+1}$.

$$A_{jm}^t\land\rho_j^t<\rho_m^t\Rightarrow\rho_j^{t+1}<\rho_m^{t+1},$$

$$A_{jm}^t\land\rho_j^t>\rho_m^t\Rightarrow\rho_j^{t+1}>\rho_m^{t+1}.$$

The same formulas apply to columns with $C$ and $\gamma$. Equal-coordinate
or newly activated lines are not made distinct by this rule. There is no
additional minimum line-separation constraint in the current formulation.

### Concurrent row and column motion

The temporary C08a restriction has been removed. Rows and columns may move
in the same logical transition, allowing diagonal atom motion. C06, C07,
and C08 remain active; the independent cardinal-motion rule C03 has been
replaced by the AOD capture/motion model.

### C10. CZ quality and unwanted-interaction isolation

The global Rydberg pulse covers every atom in the modeled grid. At the pulse
boundary only, use the intentional discrete Manhattan approximation:

$$d_{ij}(T)=|x_i^T-x_j^T|+|y_i^T-y_j^T|.$$

For the required unique unordered CZ-pair set $E$:

$$\{i,j\}\in E\Rightarrow d_{ij}(T)\le r_{\mathrm{int}},$$

$$\{i,j\}\notin E\Rightarrow d_{ij}(T)\ge r_{\mathrm{block}}.$$

The first threshold represents sufficiently good intended interaction; the
second isolates all unintended pairs, including two spectator atoms. With
$r_{\mathrm{int}}<r_{\mathrm{block}}$, intermediate distances are acceptable
for neither case at the pulse. These radius constraints are not imposed on
transport states without a pulse. The current example uses $1$ and $3$.

Diagonal motion is currently allowed even though these radii use the L1
metric. The physical interpretation of the radius metric and a possible
future restriction to cardinal movement remain open modeling questions.
Travel cost and interaction distance are distinct definitions.

## Constraint functions and experimental switches

`constraints.py` contains the named formulas. `use_constraints` in `compiler.py`
can disable individual groups to reproduce ablation experiments. All switches
are enabled in the supplied example; disabling a physical constraint changes
the model and can allow otherwise invalid schedules.

| Formulas | Python functions |
| --- | --- |
| C01 | `add_atom_bounds`, `add_initial_atom_positions` |
| C04 | `add_vertex_conflicts`, `add_swap_conflicts` |
| C05 | `add_active_line_bounds`, `add_initial_lines_off` |
| C06 | `add_line_speed_limit` |
| C07 | `add_no_motion_during_switch` |
| C08 | `add_captured_atom_motion`, `add_uncaptured_atom_wait` |
| C09 | `add_line_order` |
| C10 | `add_interaction_distance`, `add_blockade_distance` |

**Intermediate limitation:** atoms without a capturing AOD intersection simply
wait at their current coordinates; continuous trap support is not yet enforced.

## Horizon search

Use ordinary `Solver` and accept the first satisfiable horizon in the configured
ascending range. The configured upper bound is included.

The earlier MaxSMT experiment is retained in Git history. The working compiler
uses SAT search because additional trajectory optimization was too expensive
for the intended larger experiments and is not required by the layer priority.

## Validation

```sh
python3 -m unittest discover -s solver -p "test_*.py"
```

Small SAT/UNSAT cases check permitted and forbidden configurations independently
of the default example. The test suite expands with the corresponding constraints.

## Development sequence

Each row is one logical commit; the formulas and the same compiler script
evolve together. Cell numbers are zero-based indices in the local research
notebook, recorded for provenance rather than as a dependency.

| Step | Change | Original cells |
| --- | --- | --- |
| 0 | Add introductory SMT examples | 3, 5, 7 |
| 1 | Add collision-free discrete atom routing | 12 |
| 2 | Explore MaxSMT preferences for atom routing | 12, 14 |
| 3 | Support alternative target configurations with SAT routing | 16 |
| 4 | Model transport with switchable AOD rows and columns | 18 |
| 5 | Preserve the order of continuously active AOD lines | 20 |
| 6 | Allow simultaneous AOD row and column motion | 20 -> 23 (concurrent motion only) |
| 7 | Add CZ interaction and isolation distance constraints | 23 |
| 8 | Extract reusable SMT constraint functions | 25, 26 |

## Solver dependency

This implementation uses [Z3](https://github.com/Z3Prover/z3) through its Python
API. The mathematical model in this directory is developed independently in
this repository; external compiler experiments live outside this directory.
