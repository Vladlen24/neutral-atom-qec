"""Corridor routing, parking, and independent replay checks."""

import unittest
from collections import deque
from solver.routing import (
    corridor_path,
    route_transition,
    transport_actions,
    validate_route,
)


def architecture(sites, width=9, height=5):
    return {"slm_sites": sites, "width": width, "height": height}


class RoutingTests(unittest.TestCase):
    def test_astar_matches_breadth_first_search(self):
        config = architecture(
            [(0, 0), (1, 0), (3, 0), (4, 0), (0, 2), (1, 2), (3, 2), (4, 2)], 5, 4
        )
        for start in config["slm_sites"]:
            for goal in config["slm_sites"]:
                blocked = set(config["slm_sites"]) - {start, goal}
                queue, visited, expected = deque([(start, 0)]), {start}, None
                while queue:
                    point, steps = queue.popleft()
                    if point == goal:
                        expected = steps
                        break
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nxt = point[0] + dx, point[1] + dy
                        if (
                            0 <= nxt[0] < 5
                            and 0 <= nxt[1] < 4
                            and nxt not in blocked | visited
                        ):
                            visited.add(nxt)
                            queue.append((nxt, steps + 1))
                path = corridor_path(start, goal, config)
                self.assertEqual(None if path is None else len(path) - 1, expected)

    def test_two_cycles_share_one_buffer(self):
        sites = [(0, 0), (2, 0), (4, 0), (6, 0), (8, 0)]
        starts, goals = sites[:4], [sites[3], sites[2], sites[1], sites[0]]
        config = architecture(sites)
        route = route_transition(starts, goals, config)
        self.assertTrue(validate_route(starts, goals, route, config))
        self.assertEqual(
            [m["path"][-1] for m in route["moves"] if m["kind"] == "park"],
            [sites[4], sites[4]],
        )
        self.assertEqual(starts, sites[:4])

    def test_nearest_buffer_uses_corridor_distance(self):
        config = architecture([(0, 0), (2, 0), (4, 0), (8, 0)])
        starts, goals = [(0, 0), (2, 0)], [(2, 0), (0, 0)]
        route = route_transition(starts, goals, config)
        self.assertEqual(route["moves"][0]["path"][-1], (4, 0))
        self.assertTrue(validate_route(starts, goals, route, config))

    def test_full_occupancy_and_disconnected_goals_have_distinct_failures(self):
        starts = [(0, 0), (2, 0)]
        full = route_transition(starts, starts[::-1], architecture(starts))
        self.assertEqual(full["reason"], "no_parking_site")
        config = architecture([(0, 0), (1, 0), (2, 0)], 3, 1)
        blocked = route_transition([(0, 0)], [(2, 0)], config)
        self.assertEqual(blocked["reason"], "disconnected_goal")

    def test_empty_slm_cannot_be_crossed(self):
        config = architecture([(0, 0), (1, 0), (2, 0)], 3, 2)
        path = corridor_path((0, 0), (2, 0), config)
        self.assertNotIn((1, 0), path)
        self.assertEqual(len(path) - 1, 4)
        route = route_transition([(0, 0)], [(2, 0)], config)
        actions = list(transport_actions(route))
        self.assertEqual(actions[0]["action"], "pickup")
        self.assertEqual(actions[-1]["action"], "release")
        self.assertTrue(validate_route([(0, 0)], [(2, 0)], route, config))
        route["moves"][0]["path"] = [(0, 0), (1, 0), (2, 0)]
        with self.assertRaises(ValueError):
            validate_route([(0, 0)], [(2, 0)], route, config)

    def test_no_motion_and_invalid_occupancy(self):
        config = architecture([(0, 0), (2, 0)])
        route = route_transition([(0, 0)], [(0, 0)], config)
        self.assertEqual(route["moves"], [])
        self.assertTrue(validate_route([(0, 0)], [(0, 0)], route, config))
        with self.assertRaises(ValueError):
            route_transition([(0, 0), (0, 0)], [(0, 0), (2, 0)], config)
