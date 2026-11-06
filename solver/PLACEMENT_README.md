# SLM placement model

The solver assigns atom positions at gate execution. It does not model the
transitions between those positions. Every atom, including spectators, is
held in an SLM trap at every modeled layer. An optional sequential router handles
pickup, transport, and release before the next gate layer.

## Variables and common constraints

For a layer with N atoms, the solver declares two integer coordinates per atom:

$$
p_i=(x_i,y_i),\qquad i=0,\ldots,N-1.
$$

There is no transport index T, no intermediate position sequence, and no AOD
coordinate or activation variable. The fixed SLM site set is S.

**SLM support.** Every atom must occupy an available site:

$$
p_i\in\mathcal S.
$$

**Unique occupancy.** A trap cannot hold two atoms:

$$
p_i\ne p_j\qquad(i\ne j).
$$

Site coordinates are validated against the array bounds. Initial positions
must be distinct SLM sites, including for empty and global-only programs.
Initial positions are input data; local and Rydberg placements are free to
change them. No cost currently penalizes those changes.

## Gate-layer constraints

The current discrete approximation uses Manhattan distance:

$$
d_{ij}=|x_i-x_j|+|y_i-y_j|.
$$

This is an interaction-distance model, not a routing distance or calibrated
Euclidean physical radius. Changing the transport algorithm does not change
this metric automatically.

### Rydberg layers

A Boolean variable b_g selects each ready CZ operation g. Its targets are i,j:

$$
b_g\Rightarrow d_{ij}\le r_{\mathrm{int}}.
$$

For a candidate pair that is not selected:

$$
\neg b_g\Rightarrow d_{ij}\ge r_{\mathrm{block}}.
$$

Every pair that is not a candidate also obeys:

$$
d_{ij}\ge r_{\mathrm{block}}.
$$

The Rydberg pulse covers all atoms. Consequently these separation rules include
spectators and atoms belonging to different selected pairs. Exactly K
candidate gates are selected:

$$
\sum_{g\in\mathcal A} b_g=K.
$$

Ready candidates already have disjoint target sets. Repeated CZ operations
retain separate occurrence IDs and cannot bypass earlier operations on their
atoms. All atoms occupy SLM traps, not only the selected CZ endpoints.

### Local single-qubit layers

For each ready local operation g on atom i, define its isolation predicate:

$$
I_g=\bigwedge_{j\ne i}\left(d_{ij}\ge r_{\mathrm{crosstalk}}\right).
$$

Require at least K of these predicates to hold:

$$
\sum_{g\in\mathcal A}\mathbf{1}[I_g]\ge K.
$$

Execute K isolated candidates in input order. No separate selection variables
are required. Unaddressed atoms need not be isolated from each other.
The entangling and blockade constraints are inactive on local layers.

### Global single-qubit layers

A global rotation is a layer of its own. It retains the current placement,
requires no new SMT query, and applies no interaction-distance constraint.
All atoms remain in distinct SLM traps.

Rotation axes and angles are retained as operation metadata. This compiler
does not simulate quantum-state evolution.

## Scheduling

An operation becomes ready only when every preceding operation sharing any
of its atoms has completed. A global rotation involves all atoms. Candidate
selection stops at the next pending global rotation, even when other atoms
would otherwise be free.

Among ready operations, local rotations have strict priority over CZ gates.
A layer contains a single gate type. For local or Rydberg layers, try K from
the number of candidates down to one and return the first satisfiable
placement. UNKNOWN, including a solver timeout, stops compilation; it never
justifies reducing K. Failure at K=1 stops the pipeline rather than bypassing
a ready local layer.

The objective is maximum gate count in the current layer, not a proof of the
minimum total layer count. There is no route-length or movement objective.
Solver model choices may differ across Z3 versions even though the scheduling
policy and candidate order are fixed.

## Transport constraints removed from this model

| Earlier rule | Placement treatment |
| --- | --- |
| Atom bounds | Implied by validated SLM membership |
| Initial atom positions at t=0 | Input validation; no intermediate state variables |
| AOD bounds and initial state | Not modeled |
| Line motion, order, separation, and switching | Router responsibility |
| Captured motion and uncaptured waiting | Router responsibility |
| SLM-or-AOD support and release rules | Replaced by all-atom SLM support at execution |
| Vertex conflicts | Unique SLM occupancy remains |
| Swaps and swept-path safety | Router responsibility |
| Selected-pair SLM support | Subsumed by all-atom SLM support |

For the example with 10 atoms and eight AOD lines, the earlier T=10 model
would declare 396 atom/line variables plus CZ selectors. The placement model
uses 20 coordinate variables plus CZ selectors. This compares declarations,
not solver complexity or the runtime of equally complete compilation tasks.

## Sequential corridor routing

`compile_placement(..., routing=True)` checks each proposed placement with the
A* router in `routing.py`. Without this option the placement-only behavior
remains available. No transport variables are added to Z3.

Each transfer uses one active AOD row and one column. The atom follows their
intersection; only one axis moves per unit grid step. Pickup and release are
stationary actions, and the AOD is deactivated between transfers. All other
atoms remain in SLM traps. Transport occurs with gate pulses off.

A* allows the source and destination SLM sites but blocks every other SLM
site, including empty ones. Its heuristic is Manhattan distance and every
edge costs one cell. This finds shortest individual transfers, not an optimal
whole routing schedule. Velocities, beam widths, finite atom sizes, and physical
timings are not modeled.

Deliver atoms with empty destinations first, using atom index to break ties.
When the remaining destinations form occupied cycles, park one atom in an
empty SLM outside the complete target set. Choose the shortest reachable
parking path, breaking ties by site coordinates; the parking site must also
have a corridor path to that atom's final destination. Resolve the opened
cycle before another cycle needs the buffer. Parking can therefore be reused.

The router returns a complete plan or a failure reason (`disconnected_goal`,
`no_parking_site`, or `no_parking_path`). A failed trial has no physical effect:
its intermediate positions and moves are discarded. At the same layer, the
placer decreases K by one, rebuilds the placement problem, and tries routing
again from the unchanged current placement. It does not try another SMT model
at the rejected K. Failure at K=1 stops with an error; it does not certify that
all possible placements or routes are impossible. UNKNOWN still stops directly.

Only successfully routed layers remove operations from the pending list.
Every unexecuted occurrence keeps its original ID and order dependencies.
This can split a proposed layer into smaller layers; all accepted layers are
included in both the output schedule and the PNG contact sheet.

Successful routes are replayed to verify endpoints, unique occupancy, grid
bounds, unit axial motion, and the absence of intermediate SLM crossings.
`routing_verified` means verified under this discrete one-atom model.
The output retains transfer paths and parking labels. `transport_actions`
translates these paths into pickup, move-row, move-column, and release actions.

The MP4 shows the active row and column as red dashed lines, stationary pickup
and release, and temporary parking as a purple outline. Atom colors retain
their data/ancilla meaning. PNG images show only initial and gate-execution
placements. Frame duration is illustrative, not physical gate or transport time.

## Future transport extensions

Parallel routing will need shared row/column motion, line separation and order,
capacity limits, and checks of every active intersection, including empty
ones. Intermediate SLM parking and recapture may be needed. Before choosing
between pathfinding and SMT for parallel routing, benchmark the fixed-endpoint
axial transport problem and its variable/constraint counts.

Potential secondary placement objectives, after maximizing K, include the
number of atoms moved and estimated corridor distance. These remain deferred.
