"""g2048.py  --  2048, the deterministic half of it

A port of gabrielecirulli/2048 (MIT), whose `js/game_manager.js`
and `js/grid.js` are the specification followed here: the same
traversal order, the same farthest-position walk, the same rule
that a tile merged this move cannot merge again, the same score.
The chance -- the tile that appears after a move that moved
something -- is left out, so a board and a list of moves go in and
a board and a score come out, with nothing random in between.

The grid is `cells[x][y]` as the original has it: x is the column
and y the row, y growing downward, so `up` is (0, -1).  It lives in
a map keyed x * 4 + y, with an absent cell and a cell holding zero
meaning the same thing -- a map has no delete, so a tile that moves
away leaves a zero behind.

`main(board, moves)`: `board` is sixteen non-negative numbers
separated by single spaces, in cell order; `moves` is a text of the
letters `u r d l`.  Out comes one text -- the score, the number of
moves that moved something, then the sixteen final cells.
"""

# --- the four operators a map and a record are made of ---------------
#
# `map-put`, `map-get`, `put` and `get` build a new map or record
# rather than changing one; Python has no immutable dict, so they are
# written out here.  `fold` is a list operator.

def map_put(m, k, v):
    out = dict(m)
    out[k] = v
    return out

def map_get(m, k, default):
    return m[k] if k in m else default

def put(r, k, v):
    out = dict(r)
    out[k] = v
    return out

def get(r, k):
    return r[k]

def fold(f, acc, xs):
    for x in xs:
        acc = f(acc, x)
    return acc

SIZE = 4
GOAL = 2048

def ckey(x, y):
    return x * SIZE + y

def within(x, y):
    return (x >= 0 and x < SIZE) and (y >= 0 and y < SIZE)

# Out of bounds reads as empty.  Without the guard, (0, 4) and (1, 0)
# would be the same key and a tile would merge with the wrong
# neighbour at the edge of the board.
def at(b, x, y):
    return map_get(b, ckey(x, y), 0) if within(x, y) else 0

# The original's direction numbering and vectors.
def vx(d):
    return [0, 1, 0, -1][d]

def vy(d):
    return [-1, 0, 1, 0][d]

# The traversal is built so that the tiles furthest along the vector
# are visited first; that is the whole reason a row of four twos
# becomes two fours and not one eight.
def order(rev):
    return [3, 2, 1, 0] if rev else [0, 1, 2, 3]

# The last free cell along the vector, and the cell after it -- the
# original's findFarthestPosition, which walks while it is inside the
# board and empty.
def farthest(b, x, y, dx, dy):
    nx = x + dx
    ny = y + dy
    if within(nx, ny) and not at(b, nx, ny):
        return farthest(b, nx, ny, dx, dy)
    return {"fx": x, "fy": y, "nx": nx, "ny": ny}

# --- one cell of one move -------------------------------------------
#
# `st` carries the board, the cells that have already merged this move
# (the original hangs a `mergedFrom` on the tile; a tile here is a
# number and has nowhere to hang anything, so the flags are a map),
# the score, whether anything moved at all, and whether 2048 appeared.

def move_cell(st, x, y, d):
    v = at(get(st, "b"), x, y)
    if not v:
        return st
    p = farthest(get(st, "b"), x, y, vx(d), vy(d))
    n = at(get(st, "b"), get(p, "nx"), get(p, "ny"))
    if (n == v) and not map_get(get(st, "m"), ckey(get(p, "nx"), get(p, "ny")), 0):
        # the tile in front is the same and has not merged yet
        k = ckey(get(p, "nx"), get(p, "ny"))
        v2 = v * 2
        return put(put(put(put(put(st,
                                   "b", map_put(map_put(get(st, "b"), ckey(x, y), 0), k, v2)),
                               "m", map_put(get(st, "m"), k, 1)),
                           "s", get(st, "s") + v2),
                       "won", get(st, "won") or (v2 == GOAL)),
                   "moved", 1)
    # otherwise it slides as far as it can, if that is anywhere
    if (get(p, "fx") == x) and (get(p, "fy") == y):
        return st
    return put(put(st, "b", map_put(map_put(get(st, "b"), ckey(x, y), 0),
                                    ckey(get(p, "fx"), get(p, "fy")), v)),
               "moved", 1)

def sweep(w, d):
    ys = order(vy(d) == 1)
    return fold(lambda a, x:
                fold(lambda a2, y: move_cell(a2, x, y, d), a, ys),
                {"b": get(w, "board"), "m": {}, "s": get(w, "score"),
                 "moved": 0, "won": get(w, "won")},
                order(vx(d) == 1))

# --- the cells, in order --------------------------------------------
#
# In the original's order -- column by column, and within a column top
# to bottom -- because that is the order a board is written down in
# and read back out of.

def all_cells():
    return fold(lambda acc, x: acc + [ckey(x, y) for y in range(0, SIZE)],
                [], range(0, SIZE))

# A board from sixteen numbers in cell order, and back again.
def board_of(xs):
    return fold(lambda m, p: map_put(m, p[0], p[1]), {}, list(zip(all_cells(), xs)))

def cells_of(b):
    return [map_get(b, k, 0) for k in all_cells()]

# --- a text of moves ------------------------------------------------
#
# `u r d l` are the original's 0 1 2 3; anything else is a push to the
# left, which is the last of them.

def dir_of(c):
    if c == 117:
        return 0
    if c == 114:
        return 1
    if c == 100:
        return 2
    return 3

# The world a sweep reads -- the board, the score and whether 2048 has
# appeared -- together with how many moves have moved anything, which
# is what the original decides on whether to drop a new tile.

def step(g, d):
    st = sweep(get(g, "w"), d)
    return {"w": put(put(put(get(g, "w"), "board", get(st, "b")),
                         "score", get(st, "s")),
                     "won", get(st, "won")),
            "n": get(g, "n") + get(st, "moved")}

def play(g, ds):
    return fold(lambda a, d: step(a, d), g, ds)

def start(cs):
    return {"w": {"board": board_of(cs), "score": 0, "won": 0}, "n": 0}

def report(g):
    return " ".join([str(get(get(g, "w"), "score")), str(get(g, "n"))]
                    + [str(v) for v in cells_of(get(get(g, "w"), "board"))])

def main(board, moves):
    cs = [int(t) for t in board.split()]
    ds = [dir_of(c) for c in [ord(ch) for ch in moves]]
    return report(play(start(cs), ds))

def solve(board, moves):
    return main(board, moves)
