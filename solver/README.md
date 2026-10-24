# SMT compiler model

The compiler schedules unique, mutually commuting CZ interactions between
neutral atoms on a discrete grid. AOD rows and columns transport atoms;
fixed SLM sites provide stationary trapping locations. Each CZ layer ends
with a global Rydberg pulse.

The constraint functions are implemented in [`constraints.py`](constraints.py).
All groups are enabled in the supplied example. The `use_constraints`
dictionary in [`compiler.py`](compiler.py) supports experiments with individual
groups disabled.

## Notation

Within one layer, states are indexed by $t=0,\ldots,T$ and atoms by $i$.
The constraints apply to all valid atom, line, and time indices unless stated
otherwise.

| Symbol | Meaning |
| --- | --- |
| $p_i^t=(x_i^t,y_i^t)$ | Integer position of atom $i$ |
| $W,H$ | Grid width and height |
| $s_i$ | Initial atom position in the layer |
| $R_j^t,\rho_j^t$ | Enabled state and vertical coordinate of AOD row $j$ |
| $C_k^t,\gamma_k^t$ | Enabled state and horizontal coordinate of AOD column $k$ |
| $\mathcal{S}$ | Fixed SLM site set |
| $E$ | Remaining unordered CZ pairs |
| $z_e$ | Boolean selection indicator, written as 0 or 1 in sums |
| $r_{\mathrm{int}},r_{\mathrm{block}}$ | Interaction and isolation thresholds |

## Constraints

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
states as specified in constraint 11.

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

### 9. Intended interactions and isolation

At a layer's Rydberg pulse, use the discrete Manhattan distance

$$
d_{ij}(T)=|x_i^T-x_j^T|+|y_i^T-y_j^T|.
$$

For the selected CZ-pair set $E^*=\{e\in E:z_e=1\}$, require

$$
\{i,j\}\in E^*\Rightarrow d_{ij}(T)\le r_{\mathrm{int}}.
$$

$$
\{i,j\}\notin E^*\Rightarrow d_{ij}(T)\ge r_{\mathrm{block}}.
$$

The first threshold enforces sufficiently close intended CZ partners. The
second isolates every other pair, including two spectators, because the pulse
illuminates all atoms. For $r_{\mathrm{int}}<r_{\mathrm{block}}$, distances
between these thresholds are unsuitable for either case.

The bounds apply at pulse boundaries, not during pulse-free transport.
Manhattan distance is a model approximation even with diagonal motion enabled;
the radii are not calibrated physical lengths. The example uses
$r_{\mathrm{int}}=1$ and $r_{\mathrm{block}}=3$.

### 10. CZ-pair selection

For a trial layer size $K$, select exactly $K$ remaining pairs:

$$
\sum_{e\in E}z_e=K.
$$

An atom participates in at most one selected pair. For its incident edge set
$E_i=\{e\in E:i\in e\}$:

$$
\sum_{e\in E_i}z_e\le1.
$$

This creates a layer of disjoint CZ gates. Unselected candidates remain subject
to the isolation bound in constraint 9.

### 11. State continuity between layers

The next layer starts from the preceding layer's final atom and AOD states:

$$
p_{i,\ell+1}^{0}=p_{i,\ell}^{T_\ell}.
$$

$$
R_{j,\ell+1}^{0}=R_{j,\ell}^{T_\ell},\qquad
C_{k,\ell+1}^{0}=C_{k,\ell}^{T_\ell}.
$$

For enabled lines, their coordinates also carry over:

$$
R_{j,\ell}^{T_\ell}\Rightarrow\rho_{j,\ell+1}^{0}=\rho_{j,\ell}^{T_\ell}.
$$

$$
C_{k,\ell}^{T_\ell}\Rightarrow\gamma_{k,\ell+1}^{0}=\gamma_{k,\ell}^{T_\ell}.
$$

Line identities persist; inactive coordinates remain unconstrained. Executed
pairs are removed, and the remaining interactions are scheduled again:

$$
E_{\ell+1}=E_\ell\setminus E_\ell^*.
$$

The boundary state is shared, so it adds no extra transition:

$$
T_{\mathrm{total}}=\sum_\ell T_\ell.
$$

The horizon counts logical transitions. Rydberg pulses mark layer endpoints;
a separately calibrated gate duration is not included in this count.

## Scheduling priority

Let $F(K,T)$ mean that the hard constraints are satisfiable for layer size $K$
and horizon $T$. With $\mathcal{T}=\{T_{\min},\ldots,T_{\max}\}$, the search is

$$
K^*=\max\{K\ge1:\exists T\in\mathcal{T},\ F(K,T)\}.
$$

$$
T^*=\min\{T\in\mathcal{T}:F(K^*,T)\}.
$$

The number of parallel CZ gates has priority over transport duration. The
solver tries $K$ in descending order and $T$ in ascending order, accepting the
first satisfying model. If a trial cardinality is infeasible over the entire
horizon range, it decreases $K$ and allows a new choice of pairs.

The compiler uses ordinary SAT search, with no additional optimization of
individual atom movements. It optimizes each layer's priority within the
specified horizon range, rather than globally optimizing all future layers.

## Scope

The current input is a set of unique, mutually commuting CZ pairs. Full circuit
dependencies, repeated CZ operations interleaved with other gates, and
single-qubit scheduling are not yet represented. Positions and time steps are
discrete; physical capture dynamics and hardware timing require a more detailed
model.

## Tests

Run from the repository root:

```sh
python3 -m unittest discover -s solver -p "test_*.py"
```

The tests cover admissible and forbidden constraint configurations, carried
AOD state, complete CZ coverage, trap support, collisions, and interaction
distances throughout a computed schedule.
