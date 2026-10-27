# SMT compiler model

The compiler schedules local and global single-qubit rotations and CZ layers. Local rotations have strict priority among ready operations.
All layers share the AOD transport and trap-support model below.
Input rotations use `(atom, ('rx'/'ry'/'rz', angle))` or
`('global', ('rx'/'ry'/'rz', angle))`; `(i, j)` specifies a CZ gate.
Axes and angles are operation metadata; quantum-state evolution is not simulated.

The `use_constraints` dictionary enables constraint groups. Order preservation
is required in this pipeline. `layer_settings` selects each type's horizon, constraints, and builder.

## Notation

Within a layer, states are indexed by $t=0,\ldots,T$ and atoms by $i$.
The formulas apply to all valid indices unless stated otherwise.

| Symbol | Meaning |
| --- | --- |
| $p_i^t=(x_i^t,y_i^t)$ | Integer atom position |
| $W,H$ | Grid width and height |
| $s_i$ | Initial atom position in the layer |
| $R_j^t,\rho_j^t$ | Enabled state and coordinate of AOD row $j$ |
| $C_k^t,\gamma_k^t$ | Enabled state and coordinate of AOD column $k$ |
| $\mathcal S$ | Fixed SLM site set |
| $E_\ell$ | Pending operation IDs in input order |
| $A_g$ | Atoms addressed by operation $g$; all atoms for a global rotation |
| $\mathcal A_\ell$ | Candidate IDs for the selected layer type |
| $L(g)$ | Execution-layer index of operation $g$ |
| $r_{\mathrm{crosstalk}}$ | Local-addressing isolation threshold |

## Shared transport constraints

### 1. Atom bounds and initial positions

Atoms remain inside the modeled array and begin at the specified positions:

$$
0\le x_i^t<W,\qquad 0\le y_i^t<H.
$$

$$
p_i^0=s_i.
$$

### 2. AOD line domains and initial states

An enabled AOD line lies within the array. An inactive line's coordinate is
unconstrained:

$$
R_j^t\Rightarrow 0\le\rho_j^t<H.
$$

$$
C_k^t\Rightarrow 0\le\gamma_k^t<W.
$$

All lines start disabled before the first layer. Later layers inherit their
states as specified in the state-continuity constraint.

$$
R_j^0=0,\qquad C_k^0=0.
$$

### 3. Bounded AOD displacement

A continuously enabled line moves at most one grid unit per logical step:

$$
R_j^t\land R_j^{t+1}\Rightarrow |\rho_j^{t+1}-\rho_j^t|\le1.
$$

$$
C_k^t\land C_k^{t+1}\Rightarrow |\gamma_k^{t+1}-\gamma_k^t|\le1.
$$

Rows and columns can move simultaneously, allowing diagonal atom transport.
This bound represents discrete displacement, not a calibrated physical speed.

### 4. Separate line switching from transport

Let $Q_t$ indicate that any line changes its enabled state:

$$
Q_t=\left(\bigvee_j (R_j^t\ne R_j^{t+1})\right)
\lor\left(\bigvee_k (C_k^t\ne C_k^{t+1})\right).
$$

During such a transition, every continuously enabled line stays in place:

$$
Q_t\land R_j^t\land R_j^{t+1}\Rightarrow\rho_j^{t+1}=\rho_j^t.
$$

$$
Q_t\land C_k^t\land C_k^{t+1}\Rightarrow\gamma_k^{t+1}=\gamma_k^t.
$$

### 5. Capture and coupled atom motion

An atom is captured at an active row-column intersection when

$$
B_{ijk}^t=R_j^t\land C_k^t\land(y_i^t=\rho_j^t)\land(x_i^t=\gamma_k^t).
$$

If no line switches, the atom follows every capturing intersection:

$$
\neg Q_t\land B_{ijk}^t\Rightarrow
(x_i^{t+1}=\gamma_k^{t+1}\land y_i^{t+1}=\rho_j^{t+1}).
$$

An uncaptured atom, or any atom during switching, remains stationary:

$$
\left(Q_t\lor\neg\bigvee_{j,k}B_{ijk}^t\right)\Rightarrow p_i^{t+1}=p_i^t.
$$

Capture is determined by coincident coordinates. The model does not yet
represent explicit SLM-to-AOD transfer states or physical capture durations.

### 6. AOD line order

Two continuously enabled lines retain their strict order. For rows, define

$$
A_{jm}^t=R_j^t\land R_m^t\land R_j^{t+1}\land R_m^{t+1}.
$$

Then require

$$
A_{jm}^t\land(\rho_j^t<\rho_m^t)\Rightarrow\rho_j^{t+1}<\rho_m^{t+1}.
$$

$$
A_{jm}^t\land(\rho_j^t>\rho_m^t)\Rightarrow\rho_j^{t+1}>\rho_m^{t+1}.
$$

The column constraints use $C$ and $\gamma$ in the same way. These conditions
prevent order reversal during transport; they do not impose a minimum
separation or distinct coordinates on newly activated lines.

### 7. Continuous trap support

Each atom occupies either an SLM site or an active AOD intersection at every
state. With $L_i^t=(p_i^t\in\mathcal{S})$:

$$
L_i^t\lor\bigvee_{j,k}B_{ijk}^t.
$$

Turning off an active row or column passing through an atom requires the
atom to be on an SLM site, so that stationary trapping remains available:

$$
R_j^t\land\neg R_j^{t+1}\land(y_i^t=\rho_j^t)\Rightarrow L_i^t.
$$

$$
C_k^t\land\neg C_k^{t+1}\land(x_i^t=\gamma_k^t)\Rightarrow L_i^t.
$$

### 8. Atom collisions

Two atoms cannot occupy the same grid site:

$$
p_i^t\ne p_j^t\qquad(i<j).
$$

They also cannot exchange sites in one transition:

$$
\neg(p_i^t=p_j^{t+1}\land p_j^t=p_i^{t+1})\qquad(i<j,\ t<T).
$$

These constraints cover sampled positions and direct swaps. They do not
resolve all possible collisions along continuous trajectories between states.

## Operation order and candidate selection

Repeated occurrences have distinct original input IDs. Operations sharing an
atom retain their input order:

$$
h<g,\quad A_h\cap A_g\ne\varnothing\Rightarrow L(h)<L(g).
$$

For each pending operation, define its unexecuted predecessors:

$$
D_\ell(g)=\{h\in E_\ell:h<g,\ A_h\cap A_g\ne\varnothing\}.
$$

The ready set is

$$
\mathcal F_\ell=\{g\in E_\ell:D_\ell(g)=\varnothing\}.
$$

A global rotation addresses all atoms. Every earlier operation must complete
before it, and every later operation waits until it completes. It occupies a
separate layer. Within a local layer, candidates address distinct atoms.

The candidate type is chosen before the K/T search. Ready local rotations have
strict priority over ready CZ gates, including independent CZ gates appearing
earlier in the input. If any local operation is ready, $\mathcal A_\ell$ contains
the ready local operations; otherwise it contains ready CZ operations. A ready
global rotation is the sole candidate. Skipped operations still prevent their
successors from advancing on shared atoms.

| Layer type | Default T range | Additional constraints | Selection |
| --- | --- | --- | --- |
| local | 2..10 | Crosstalk isolation | Isolation predicates |
| rydberg | 2..10 | CZ interaction and blockade distances | `chosen` per operation |
| global | 0 | None | One rotation |

`layer_settings` associates each type with its horizon, constraint names, and
builder function. `LAYER_PRIORITY` lists the order of ready nonglobal types.
The common transport model and K/T search are shared across these types.

## Local rotations and crosstalk

At a gate-execution endpoint, use Manhattan distance:

$$
d_{ij}(T)=|x_i^T-x_j^T|+|y_i^T-y_j^T|.
$$

For a local candidate $g$ addressing atom $i_g$, define

$$
C_g(T)=\bigwedge_{j\ne i_g}[d_{i_gj}(T)\ge r_{\mathrm{crosstalk}}].
$$

This isolates the addressed atom from every other atom, including targets of
other simultaneous local rotations. Two unaddressed spectators need not be
separated by this threshold. The condition applies when the local gates execute,
not during transport. The supplied example uses $r_{\mathrm{crosstalk}}=2$.

For a trial layer size K, require at least K admissible candidates:

$$
\sum_{g\in\mathcal A_\ell}\mathbf 1[C_g(T)]\ge K.
$$

When all candidates are requested, each $C_g(T)$ is asserted directly. Otherwise
a pseudo-Boolean cardinality constraint is used. After SAT, execute K admissible
operations and retain every other operation in input order. No explicit `chosen`
variables are needed for local layers: candidates already address distinct atoms,
and local eligibility depends only on their endpoint isolation predicates.

## CZ interactions and global Rydberg illumination

CZ candidates have disjoint atom pairs $e_g=A_g$. With Boolean indicators $z_g$,
select exactly K operations:

$$
\sum_{g\in\mathcal A_\ell}z_g=K.
$$

An atom participates in at most one selected operation:

$$
\sum_{\{g\in\mathcal A_\ell:i\in A_g\}}z_g\le1.
$$

The dependency frontier already provides disjoint candidates. For the selected
physical pair set $E^*=\{e_g:z_g=1\}$, require

$$
\{i,j\}\in E^*\Rightarrow d_{ij}(T)\le r_{\mathrm{int}}.
$$

$$
\{i,j\}\notin E^*\Rightarrow d_{ij}(T)\ge r_{\mathrm{block}}.
$$

The intended interaction bound ensures close CZ partners. The isolation bound
applies to every other pair, including spectators, because the Rydberg pulse
illuminates the entire array. The example uses $r_{\mathrm{int}}=1$ and
$r_{\mathrm{block}}=3$. Repeated CZ occurrences remain separate operations and
cannot share a layer; physical pair sets are used only for distance constraints.

CZ-distance constraints apply only to Rydberg layers; crosstalk isolation applies
only to local layers. Global rotations apply neither distance rule.

## State continuity and global rotations

Each layer starts from the preceding layer's final atom and AOD state:

$$
p_{i,\ell+1}^0=p_{i,\ell}^{T_\ell}.
$$

$$
R_{j,\ell+1}^0=R_{j,\ell}^{T_\ell},\qquad C_{k,\ell+1}^0=C_{k,\ell}^{T_\ell}.
$$

Coordinates of enabled lines also carry over:

$$
R_{j,\ell}^{T_\ell}\Rightarrow\rho_{j,\ell+1}^0=\rho_{j,\ell}^{T_\ell}.
$$

$$
C_{k,\ell}^{T_\ell}\Rightarrow\gamma_{k,\ell+1}^0=\gamma_{k,\ell}^{T_\ell}.
$$

Line identities persist. A global rotation keeps all these states unchanged,
requires no transport search, and has $T_\ell=0$. The initial state is validated
even for an empty program or an initial global rotation.

Only executed operation IDs $G_\ell^*$ are removed:

$$
E_{\ell+1}=E_\ell\setminus G_\ell^*.
$$

Pending IDs retain their input order. Adjacent layers share their boundary frame,
and the total number of transport transitions is

$$
T_{\mathrm{total}}=\sum_\ell T_\ell.
$$

Gate events retain separate layer indices even when they share a transport step.
Their physical durations are not yet included in this transport count.

## Scheduling priority

Let $F(K,T)$ mean the selected layer type is feasible, and let $\mathcal T$ be
its configured horizon range. The search implements

$$
K^*=\max\{K\ge1:\exists T\in\mathcal T,\ F(K,T)\}.
$$

$$
T^*=\min\{T\in\mathcal T:F(K^*,T)\}.
$$

The compiler tries K in descending order and T in ascending order, returning
the first satisfying model. If a cardinality is infeasible across the entire
range, it tries a different subset of smaller size. UNKNOWN is reported as a
solver failure; it is not treated as UNSAT. The search optimizes each layer's
priority within the horizon range, without globally optimizing the full schedule
or individual atom movements.

If the local search is UNSAT for every K/T, compilation stops with a diagnostic.
It does not switch to a CZ layer to change the geometry.

## Scope and output

The current model uses a single discrete array with horizontal, vertical, and
diagonal transport. Manhattan distance is an explicit approximation when diagonal
movement is allowed; radii are not calibrated physical lengths. Zoned geometry,
capture dynamics, pulse durations, and hardware timing are not yet modeled.
Rotation axes and angles are retained without simulating a quantum state.

`compile_schedule` returns `architecture`, `paths`, `rows`, `columns`, `layers`,
`operation_layers`, and `total_steps`. Each layer records its type, transport
endpoint, duration, original operation IDs, and gate parameters.

Run checks from the repository root:

```sh
python3 -m unittest discover -s solver -p "test_*.py"
```

Tests cover gate dependencies, repeated occurrences, admissible and forbidden
physical configurations, crosstalk, state continuity, and complete schedules.
