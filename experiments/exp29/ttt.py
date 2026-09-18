"""ttt.py  --  the noughts-and-crosses search of experiments/exp29/ttt.lova,
transliterated function for function into Python (Exp 29).

The input is nine characters from ".XO", square 0 first, row by row, so
square 4 is the centre.  The side to move is X when X and O have equal
counts, else O.  The value is one text: the chosen square, a space, and
the score for the side to move (1 a forced win, 0 a draw, -1 a forced
loss), e.g. "4 0".  A position already decided answers "-1 " and the
winner (1 X, 2 O, 0 a draw).

The board is one integer in base 3: square k (0..8) is digit k, and a
digit is 0 empty, 1 X, 2 O.

Naming: the LOVA program's search function is called `solve`, and the
harness wants `solve(board)` to be the entry point, so the search is
`solve_position` here and `solve` is the entry point at the bottom.
The LOVA record `(rec score s memo m)` is a dict {"score": s, "memo": m};
the memo is threaded linearly (the version put into is never read
again), so `map-put` is an in-place assignment that returns the dict.
"""


def powers():
    return [1, 3, 9, 27, 81, 243, 729, 2187, 6561]


def cell(b, k):
    return (b // powers()[k]) % 3


# Only ever called on an empty square, so adding is setting.
def place(b, k, v):
    return b + v * powers()[k]


def lines():
    return [[0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]]


# Who holds all three squares of a line, or 0.
def line_owner(b, l):
    a = cell(b, l[0])
    return a if (a == cell(b, l[1]) and a == cell(b, l[2])) else 0


def winner(b):
    w = 0
    for l in lines():
        w = w or line_owner(b, l)
    return w


def empties(b):
    return [k for k in range(0, 9) if not cell(b, k)]


def full(b):
    return not empties(b)


def other(p):
    return 3 - p


# --- the search -----------------------------------------------------
#
# `solve_position` scores a position for the player about to move: 1 a
# forced win, 0 a draw, -1 a forced loss.  Positions are memoised in a
# map keyed by board and player, and the map is threaded through the
# search as a value: every call returns a record {"score": s, "memo":
# m}, and the folds below carry {"score": b, "move": k, "memo": m} and
# read their fields by name.  The first move searches the whole game;
# every later move finds its answers already there.

def memo_key(b, p):
    return b * 3 + p


def solve_position(b, p, memo):
    known = memo.get(memo_key(b, p), 5)
    if known != 5:
        return {"score": known, "memo": memo}
    if winner(b):                                   # the other side just won
        r = {"score": -1, "memo": memo}
    elif full(b):
        r = {"score": 0, "memo": memo}
    else:
        r = best(b, p, memo)
    r["memo"][memo_key(b, p)] = r["score"]
    return dict(r, memo=r["memo"])


# The best score `p` can reach from `b`, with the memo it built.
def best(b, p, memo):
    st = {"score": -2, "memo": memo}
    for k in empties(b):
        r = solve_position(place(b, k, p), other(p), st["memo"])
        st = {"score": max(st["score"], -r["score"]),
              "memo": r["memo"]}
    return st


# The square to play: {"score": s, "move": k, "memo": m}.
def choose(b, p, memo):
    st = {"score": -2, "move": -1, "memo": memo}
    for k in empties(b):
        r = solve_position(place(b, k, p), other(p), st["memo"])
        sc = -r["score"]
        if sc > st["score"]:
            st = {"score": sc, "move": k, "memo": r["memo"]}
        else:
            st = dict(st, memo=r["memo"])
    return st


# --- the text interface ---------------------------------------------
#
# Nine characters in, one line out.  A digit is read from a character:
# 88 is "X", 79 is "O", anything else is empty.  X moves when the two
# counts are equal.

def main(board):
    cs = [ord(c) for c in board]
    b = 0
    for k in range(0, 9):
        b = b + (1 if cs[k] == 88 else 2 if cs[k] == 79 else 0) * powers()[k]
    xs = len([k for k in range(0, 9) if cell(b, k) == 1])
    os_ = len([k for k in range(0, 9) if cell(b, k) == 2])
    p = 1 if xs == os_ else 2
    if winner(b) or full(b):
        return " ".join(["-1", str(winner(b))])
    r = choose(b, p, {})
    return " ".join([str(r["move"]), str(r["score"])])


def solve(board):
    return main(board)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(solve(sys.argv[1]))
