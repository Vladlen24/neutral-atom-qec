"""Sequential AOD transport through corridors between fixed SLM traps."""

from heapq import heappop, heappush


# Single-atom corridor paths
# ========================================================================
def corridor_path(start, goal, architecture):
    """Return a shortest axial path; only the endpoint SLM sites are traversable."""
    start, goal = tuple(start), tuple(goal)
    blocked = set(map(tuple, architecture["slm_sites"])) - {start, goal}
    width, height = architecture["width"], architecture["height"]

    def heuristic(point):
        return abs(point[0] - goal[0]) + abs(point[1] - goal[1])

    frontier = [(heuristic(start), 0, start)]
    cost, parent = {start: 0}, {start: None}
    while frontier:
        _, distance, point = heappop(frontier)
        if distance != cost[point]:
            continue
        if point == goal:
            path = []
            while point is not None:
                path.append(point)
                point = parent[point]
            return path[::-1]
        x, y = point
        for neighbor in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = neighbor
            if not (0 <= nx < width and 0 <= ny < height) or neighbor in blocked:
                continue
            candidate = distance + 1
            if candidate < cost.get(neighbor, float("inf")):
                cost[neighbor], parent[neighbor] = candidate, point
                heappush(
                    frontier, (candidate + heuristic(neighbor), candidate, neighbor)
                )
    return None


# Sequential transfers and cycle parking
# ========================================================================
def route_transition(starts, goals, architecture):
    """Plan a whole transition without changing the caller's physical state.

    Deliver atoms whose destinations are empty first. Break a remaining cycle
    by parking one atom outside the complete goal set. Choose the shortest
    reachable parking path, breaking ties by site coordinates. Failure returns
    a diagnostic trial plan; none of its moves should be executed.
    """
    current, goals = list(map(tuple, starts)), list(map(tuple, goals))
    sites = set(map(tuple, architecture["slm_sites"]))
    if len(current) != len(goals) or not current:
        raise ValueError(
            "Starts and goals must contain the same positive number of atoms."
        )
    for positions in (current, goals):
        if len(set(positions)) != len(positions) or not set(positions) <= sites:
            raise ValueError("Every atom must occupy a distinct SLM site.")
    if any(
        not (0 <= x < architecture["width"] and 0 <= y < architecture["height"])
        for x, y in sites
    ):
        raise ValueError("SLM sites must lie inside the routing grid.")
    moves = []

    def result(success, reason=None):
        return {
            "success": success,
            "reason": reason,
            "moves": moves,
            "positions": list(current),
            "failed_atoms": [i for i in range(len(goals)) if current[i] != goals[i]],
        }

    def transfer(atom, path, kind):
        moves.append({"atom": atom, "kind": kind, "path": path})
        current[atom] = path[-1]

    while True:
        pending = [i for i in range(len(goals)) if current[i] != goals[i]]
        if not pending:
            return result(True)
        occupied = set(current)
        ready = [i for i in pending if goals[i] not in occupied]
        if ready:
            atom = ready[0]
            path = corridor_path(current[atom], goals[atom], architecture)
            if path is None:
                return result(False, "disconnected_goal")
            transfer(atom, path, "transfer")
            continue

        # All remaining destinations are occupied: open one permutation cycle.
        atom = current.index(goals[pending[0]])
        buffers = sites - occupied - set(goals)
        if not buffers:
            return result(False, "no_parking_site")
        choices = []
        for site in sorted(buffers):
            path = corridor_path(current[atom], site, architecture)
            if (
                path is not None
                and corridor_path(site, goals[atom], architecture) is not None
            ):
                choices.append((len(path) - 1, site, path))
        if not choices:
            return result(False, "no_parking_path")
        _, _, path = min(choices)
        transfer(atom, path, "park")


# Executable AOD actions and replay validation
# ========================================================================
def transport_actions(route):
    """Yield one active row/column pair, with stationary pickup and release."""
    for move in route["moves"]:
        atom, path = move["atom"], move["path"]
        yield {
            "action": "pickup",
            "atom": atom,
            "position": path[0],
            "kind": move["kind"],
        }
        for before, after in zip(path, path[1:]):
            yield {
                "action": "move_column" if before[0] != after[0] else "move_row",
                "atom": atom,
                "position": after,
                "kind": move["kind"],
            }
        yield {
            "action": "release",
            "atom": atom,
            "position": path[-1],
            "kind": move["kind"],
        }


def validate_route(starts, goals, route, architecture):
    """Replay a successful plan, checking occupancy and each swept unit segment."""
    if not route["success"]:
        raise ValueError("Cannot execute an unsuccessful trial route.")
    current = list(map(tuple, starts))
    sites = set(map(tuple, architecture["slm_sites"]))
    for move in route["moves"]:
        atom, path = move["atom"], list(map(tuple, move["path"]))
        if len(path) < 2 or path[0] != current[atom] or path[-1] not in sites:
            raise ValueError("Invalid transfer endpoints.")
        others = set(current[:atom] + current[atom + 1 :])
        for index, (x, y) in enumerate(path):
            if not (0 <= x < architecture["width"] and 0 <= y < architecture["height"]):
                raise ValueError("Transport leaves the grid.")
            if (x, y) in others or (0 < index < len(path) - 1 and (x, y) in sites):
                raise ValueError("Transport hits an atom or passes over an SLM site.")
            if index and abs(x - path[index - 1][0]) + abs(y - path[index - 1][1]) != 1:
                raise ValueError("Transport must use unit axial segments.")
        current[atom] = path[-1]
    if current != list(map(tuple, goals)) or current != list(
        map(tuple, route["positions"])
    ):
        raise ValueError("Transport does not reach the requested placement.")
    return True
