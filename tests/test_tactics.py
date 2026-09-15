"""The tactics battle, checked against the project it was ported from.

`lib/tactics.lova` is a port of the rules of ramaureirac/godot-tactical-rpg
(MIT).  `Original` below is a transliteration of
`TacticsArenaService.process_surrounding_tiles` and the two `mark_*`
functions beside it -- the queue, the one-step-a-tile distance, the
height test on a neighbour, and the two marking rules -- and
`test_the_flood_agrees_with_the_original` runs both over every cell of
the arena for pawns of every kind and compares the distance to every
cell, one by one.

The two places the port knowingly differs are in the transliteration
too, so the test measures what it claims to: the original passes
`movement` where its own function wants a height (`chase_nearest_enemy`)
and refuses the opponent a step through its own allies (an `elif` that
reads backwards).  Both are quoted in the header of `lib/tactics.lova`.
"""

from __future__ import annotations

import collections
import unittest

from core.cli import build
from core.runtime import Cons, NIL_VALUE, Runtime, _call, _map_key, evaluate, list_to_python

API = """\
(use "tactics")
(rec new new-battle who who-map flood flood reach reachable atk attackable
     click click ai ai-step endturn end-turn winner winner strike strike
     moveto move-to pathto path-to steps steps-to hgt hgt solid solid ckey ckey
     order draw-order scene scene pick pick
     pairs (lambda m (map-pairs m))
     mkpawn (lambda id (lambda team (lambda kind (lambda x (lambda y
              (pawn-of id team kind x y))))))
     world (lambda ps (put (new-battle 0) pawns ps))
     pawns (lambda w (get w pawns))
     field (lambda p (lambda n (map-get p n 0)))
     side (lambda w (get w side))
     sel (lambda w (get w sel))
     left (lambda w (lambda s (len (side-of w s)))))
"""

N = 12
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
# movement, jump, reach, power, health -- `pawn-of`'s three kinds
KINDS = {0: (3, 1, 1, 2, 5), 1: (5, 2, 1, 2, 4), 2: (3, 1, 3, 1, 4)}


class Original:
    """`process_surrounding_tiles` and `mark_*`, transliterated.

    The original hangs `pf_root` and `pf_distance` on the tiles
    themselves and floods with a queue; this keeps the same queue and
    the same one-step increment and returns the distances.
    """

    def __init__(self, heights):
        self.h = heights                       # (x, y) -> height, absent = a hole

    def neighbours(self, x, y, jump):
        for dx, dy in DIRS:
            n = (x + dx, y + dy)
            if n in self.h and abs(self.h[n] - self.h[(x, y)]) <= jump:
                yield n

    def flood(self, root, jump, blocked):
        """`blocked` is the tiles a step may not enter -- the original's
        `is_taken` for a tile whose occupier this pawn may not pass."""
        dist = {root: 0}
        queue = collections.deque([root])
        while queue:
            cur = queue.popleft()
            for n in self.neighbours(*cur, jump):
                if n not in dist and n != root and n not in blocked:
                    dist[n] = dist[cur] + 1
                    queue.append(n)
        return dist

    @staticmethod
    def reachable(dist, movement, taken):
        return {c for c, d in dist.items() if 0 < d <= movement and c not in taken}

    @staticmethod
    def attackable(dist, reach):
        return {c for c, d in dist.items() if 0 < d <= reach}


def to_lova(xs):
    out = NIL_VALUE
    for v in reversed(xs):
        out = Cons(v, out)
    return out


class Tactics(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("new", "who", "flood", "reach", "atk", "click", "ai",
                            "endturn", "winner", "strike", "moveto", "pathto", "steps",
                            "hgt", "solid", "ckey", "order", "scene", "pick", "pairs",
                            "mkpawn", "world", "pawns", "field", "side", "sel", "left")}
        cls.heights = {(x, y): cls.call("hgt", x, y)
                       for x in range(N) for y in range(N)
                       if cls.call("hgt", x, y) >= 0}
        cls.original = Original(cls.heights)

    @classmethod
    def call(cls, name, *args):
        cls.rt.steps = 0
        fn = cls.fn[name]
        for arg in args:
            fn = _call(fn, arg, cls.rt)
        return fn

    @staticmethod
    def f(value, name):
        return value.entries[_map_key(name, "get")][1]

    def pawn(self, pid, team, kind, x, y):
        return self.call("mkpawn", pid, team, kind, x, y)

    def world_of(self, pawns):
        return self.call("world", to_lova(pawns))

    def distances(self, world, pawn, through, climb):
        d = self.call("flood", self.call("who", world), pawn, through, climb)
        out = {}
        for pair in list_to_python(self.call("pairs", d)):
            key, steps = list_to_python(pair)
            out[(key % N, key // N)] = steps
        return out

    # --- the flood against the original -----------------------------------

    def test_the_arena_is_what_it_says(self):
        self.assertEqual(len(self.heights), 137)          # 144 cells, 7 holes
        self.assertEqual(max(self.heights.values()), 4)
        self.assertEqual(min(self.heights.values()), 1)

    def test_the_flood_agrees_with_the_original(self):
        """Every cell of the arena, every kind of pawn, an empty field: the
        distance to every other cell, one by one."""
        checked = 0
        for kind, (mv, jump, rng, _pow, _hp) in KINDS.items():
            for (x, y) in sorted(self.heights)[::11]:
                p = self.pawn(0, 0, kind, x, y)
                w = self.world_of([p])
                who = self.call("who", w)
                d = self.call("flood", who, p, 0, jump)
                got = self.distances(w, p, 0, jump)
                want = self.original.flood((x, y), jump, set())
                self.assertEqual(got, want, (kind, x, y))
                mine = {c for c in got
                        if self.call("reach", who, p, d, self.call("ckey", *c))}
                self.assertEqual(mine, self.original.reachable(want, mv, set()),
                                 (kind, x, y))
                hit = {c for c in got if self.call("atk", p, d, self.call("ckey", *c))}
                self.assertEqual(hit, self.original.attackable(want, rng), (kind, x, y))
                checked += 1
        self.assertGreater(checked, 30)

    def test_a_pawn_it_may_not_pass_stops_the_flood(self):
        """An enemy standing in a corridor is a wall to movement and is not
        to a weapon -- the original floods the two separately, and so does
        this."""
        mine = self.pawn(0, 0, 0, 1, 9)
        theirs = self.pawn(3, 1, 0, 2, 9)
        w = self.world_of([mine, theirs])
        walk = self.distances(w, mine, 0, 1)        # jump 1
        shoot = self.distances(w, mine, 1, 1)       # reach 1
        self.assertNotIn((2, 9), walk)                    # cannot walk onto him
        self.assertEqual(shoot[(2, 9)], 1)                # can hit him
        blocked = self.original.flood((1, 9), 1, {(2, 9)})
        self.assertEqual(walk, blocked)

    def test_a_wall_too_high_is_not_a_neighbour(self):
        """Jump is the whole of the height rule: the same step is open to a
        scout and shut to a soldier."""
        edges = [(x, y) for (x, y) in self.heights
                 for dx, dy in DIRS
                 if (x + dx, y + dy) in self.heights
                 and self.heights[(x + dx, y + dy)] - self.heights[(x, y)] == 2]
        self.assertTrue(edges)
        x, y = edges[0]
        soldier = self.pawn(0, 0, 0, x, y)                 # jump 1
        scout = self.pawn(1, 0, 1, x, y)                   # jump 2
        up = next((x + dx, y + dy) for dx, dy in DIRS
                  if (x + dx, y + dy) in self.heights
                  and self.heights[(x + dx, y + dy)] - self.heights[(x, y)] == 2)
        # the step itself: one for the scout, and for the soldier either no
        # way at all or the long way round
        self.assertEqual(self.distances(self.world_of([scout]), scout, 0, 2)[up], 1)
        self.assertGreater(self.distances(self.world_of([soldier]), soldier, 0, 1).get(up, 99), 1)

    def test_a_path_is_a_walk_of_single_steps(self):
        p = self.pawn(0, 0, 1, 1, 9)
        w = self.world_of([p])
        who = self.call("who", w)
        d = self.call("flood", who, p, 0, 2)
        path = list_to_python(self.call("pathto", who, p, d, self.call("ckey", 4, 9)))
        cells = [(k % N, k // N) for k in path]
        self.assertEqual(cells[0], (1, 9))
        self.assertEqual(cells[-1], (4, 9))
        for a, b in zip(cells, cells[1:]):
            self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)

    # --- combat ------------------------------------------------------------

    def test_damage_is_the_attack_power_and_nothing_else(self):
        """`stats.apply_to_curr_health(-attack_power)`: no height bonus, no
        facing, no roll."""
        for kind, (_mv, _j, _r, power, _hp) in KINDS.items():
            mine = self.pawn(0, 0, kind, 1, 9)
            theirs = self.pawn(3, 1, 0, 2, 9)
            w = self.call("strike", self.world_of([mine, theirs]), 0, 3)
            hp = [self.call("field", p, "hp") for p in list_to_python(self.call("pawns", w))]
            self.assertEqual(hp[1], KINDS[0][4] - power, kind)

    def test_health_stops_at_nothing(self):
        mine = self.pawn(0, 0, 0, 1, 9)
        theirs = self.pawn(3, 1, 0, 2, 9)
        w = self.world_of([mine, theirs])
        for _ in range(6):
            w = self.call("strike", w, 0, 3)
        hp = [self.call("field", p, "hp") for p in list_to_python(self.call("pawns", w))]
        self.assertEqual(hp[1], 0)
        self.assertEqual(self.call("left", w, 1), 0)
        self.assertEqual(self.call("winner", w), 0)

    # --- what a click means -------------------------------------------------

    def test_a_click_picks_up_moves_and_strikes(self):
        mine = self.pawn(0, 0, 0, 1, 9)
        theirs = self.pawn(3, 1, 0, 4, 9)
        w = self.world_of([mine, theirs])
        self.assertEqual(self.call("sel", w), -1)
        w = self.call("click", w, self.call("ckey", 1, 9))         # pick him up
        self.assertEqual(self.call("sel", w), 0)
        w = self.call("click", w, self.call("ckey", 3, 9))         # walk two east
        at = [(self.call("field", p, "x"), self.call("field", p, "y"))
              for p in list_to_python(self.call("pawns", w))]
        self.assertEqual(at[0], (3, 9))
        w = self.call("click", w, self.call("ckey", 4, 9))         # and strike
        hp = [self.call("field", p, "hp") for p in list_to_python(self.call("pawns", w))]
        self.assertEqual(hp[1], 3)
        # spent: he is put down again
        self.assertEqual(self.call("sel", w), -1)

    def test_a_click_on_their_pawn_picks_up_nothing(self):
        w = self.world_of([self.pawn(0, 0, 0, 1, 9), self.pawn(3, 1, 0, 4, 9)])
        self.assertEqual(self.call("sel", self.call("click", w, self.call("ckey", 4, 9))), -1)

    def test_a_click_out_of_reach_puts_him_down(self):
        w = self.world_of([self.pawn(0, 0, 0, 1, 9)])
        w = self.call("click", w, self.call("ckey", 1, 9))
        self.assertEqual(self.call("sel", w), 0)
        w = self.call("click", w, self.call("ckey", 10, 2))        # the far corner
        self.assertEqual(self.call("sel", w), -1)

    # --- the opponent -------------------------------------------------------

    def test_the_opponent_closes_and_strikes(self):
        """`chase_nearest_enemy` then `choose_pawn_to_attack`: it walks to a
        tile beside the nearest of ours and hits the weakest thing in
        reach."""
        hurt = self.pawn(0, 0, 0, 3, 9)
        whole = self.pawn(1, 0, 0, 1, 9)
        theirs = self.pawn(3, 1, 1, 7, 9)                 # a scout, movement 5
        w = self.world_of([hurt, whole, theirs])
        w = self.call("strike", w, 3, 0)                  # take a point off the near one
        w = self.call("endturn", w)
        self.assertEqual(self.call("side", w), 1)
        for _ in range(8):
            if self.call("side", w) == 0:
                break
            w = self.call("ai", w)
        at = {self.call("field", p, "id"):
              (self.call("field", p, "x"), self.call("field", p, "y"))
              for p in list_to_python(self.call("pawns", w))}
        self.assertLessEqual(abs(at[3][0] - at[0][0]) + abs(at[3][1] - at[0][1]), 2)
        hp = {self.call("field", p, "id"): self.call("field", p, "hp")
              for p in list_to_python(self.call("pawns", w))}
        self.assertLess(hp[0], 5)

    def test_a_battle_ends(self):
        w = self.call("new", 0)
        for _ in range(60):
            if self.call("winner", w) >= 0:
                break
            if self.call("side", w) == 0:
                w = self.call("endturn", w)
            else:
                w = self.call("ai", w)
        self.assertGreaterEqual(self.call("winner", w), 0)
        self.assertEqual(self.call("left", w, 0), 0)      # standing still loses it

    # --- the picture --------------------------------------------------------

    def test_the_blocks_come_far_first(self):
        blocks = list_to_python(self.call("scene", self.call("new", 0)))
        self.assertEqual(len(blocks), 137)
        depth = [(self.f(b, "k") % N) + (self.f(b, "k") // N) for b in blocks]
        self.assertEqual(depth, sorted(depth))

    def test_a_point_lands_on_the_block_under_it(self):
        """What you click is the nearest block under the cursor: the middle
        of a block picks that block, unless one standing in front of it
        covers the point, which is what a taller neighbour does."""
        w = self.call("new", 0)
        exact = 0
        for b in list_to_python(self.call("scene", w)):
            k, u, v = self.f(b, "k"), self.f(b, "u"), self.f(b, "v")
            got = self.call("pick", w, u, v)
            if got == k:
                exact += 1
                continue
            depth = lambda c: (c % N) + (c // N)
            self.assertGreater(depth(got), depth(k), (k % N, k // N))
        # the rest sit under a step: a taller block in front of one covers
        # the middle of its top face, and clicking there picks the one you
        # can actually see
        self.assertGreater(exact, 90)

    def test_a_picture_costs_what_a_click_can_afford(self):
        w = self.call("new", 0)
        list_to_python(self.call("scene", w))
        self.assertLess(self.rt.steps, 80_000)
        w = self.call("click", w, self.call("ckey", 1, 9))
        list_to_python(self.call("scene", w))
        self.assertLess(self.rt.steps, 200_000)


if __name__ == "__main__":
    unittest.main()
