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

Current stage: **Explore MaxSMT preferences for atom routing**.

### C01. Atom bounds and initial positions

$$\forall i,t:\quad 0\le x_i^t<W,\quad0\le y_i^t<H,\qquad p_i^0=s_i.$$

### C02. Fixed terminal positions

$$\forall i:\quad p_i^T=f_i.$$

### C03. Independent cardinal motion or waiting

$$p_i^{t+1}-p_i^t\in\{(0,0),(1,0),(-1,0),(0,1),(0,-1)\}.$$

This preliminary routing model does not yet couple atoms through AOD lines.

### C04. Vertex and swap conflicts

$$\forall i<j,t:\quad p_i^t\ne p_j^t.$$

$$\forall i<j,t<T:\quad
\neg(p_i^t=p_j^{t+1}\land p_j^t=p_i^{t+1}).$$

These are discrete vertex/swap constraints. They do not prove collision
avoidance along every continuous trajectory between sampled states.

## Horizon search

Use ordinary `Solver` and accept the first satisfiable horizon in the configured
ascending range. The upper bound is excluded by `range(MIN_STEPS, MAX_STEPS)`.

## Historical MaxSMT experiment

At the first satisfiable routing horizon $T$, preserve all hard constraints
and maximize these soft objectives in lexicographic order:

$$\max_{\mathrm{lex}}\left(
\sum_{i,t<T}[p_i^{t+1}=p_i^t],\quad
\sum_{i,1\le t\le T}[p_i^t=f_i]\right).$$

The first objective minimizes individual atom movements at this fixed $T$;
the second prefers occupation of target sites. It is not a separate search
over $T$. This is an exploratory intermediate implementation, not a requirement
for the later SAT compiler.

## Development sequence

Each row is one logical commit; the formulas and the same compiler script
evolve together. Cell numbers are zero-based indices in the local research
notebook, recorded for provenance rather than as a dependency.

| Step | Change | Original cells |
| --- | --- | --- |
| 0 | Add introductory SMT examples | 3, 5, 7 |
| 1 | Add collision-free discrete atom routing | 12 |
| 2 | Explore MaxSMT preferences for atom routing | 12, 14 |

## Solver dependency

This implementation uses [Z3](https://github.com/Z3Prover/z3) through its Python
API. The mathematical model in this directory is developed independently in
this repository; external compiler experiments live outside this directory.
