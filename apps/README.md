# LOVA — first programs

The first real LOVA programs.  Everything in `corpus/` and
`experiments/` is either benchmark input or test harness; the files
here are **LOVA code that exists to do something**, not to prove
LOVA exists.

## Running them

Since M11 there is a command line, so none of these needs its Python
driver any more:

```
python -m core.cli run apps/is_prime.lova 1999
python -m core.cli run apps/palindrome.lova racecar
python -m core.cli analyze apps/collatz.lova 27
python -m core.cli emit apps/coprime.lova 14 15 --form stage2
```

A `{placeholder}` in a program is filled positionally from the command
line; an argument that is not an integer is quoted as a string literal,
which is how `palindrome.lova racecar` works.  The `.py` drivers are
kept because each prints a little more of the pipeline than the CLI
does, but they are no longer the way in.

## Programs

### `is_perfect.lova`

Classify an integer as a number-theoretic *perfect* number
(σ(n) = 2n; examples 6, 28, 496, 8128).

```
(let 0 {n}
  (if-surprise
    (surprise
      (merge (ref 0) (ref 0))      ; predicted: 2n (if perfect)
      (sigma (ref 0)))             ; actual:    sigma(n)
    0                              ; non-zero surprise -> not perfect
    1))                            ; zero surprise     -> PERFECT
```

Run:

```
PYTHONPATH=. python apps/is_perfect.py 6     # -> 1 (perfect)
PYTHONPATH=. python apps/is_perfect.py 12    # -> 0 (not perfect, deviation=4)
PYTHONPATH=. python apps/is_perfect.py 28    # -> 1
PYTHONPATH=. python apps/is_perfect.py 496   # -> 1
```

### `coprime.lova`

Two integers are coprime iff their gcd is 1.  Shorter than
`is_perfect`; shows that `surprise` works as a general-purpose
equality check against any literal.

```
(if-surprise
  (surprise 1 (gcd {a} {b}))       ; |1 - gcd(a,b)|
  0                                ; non-zero surprise -> not coprime
  1)                               ; zero surprise     -> coprime
```

Run:

```
PYTHONPATH=. python apps/coprime.py 7 13     # -> 1 (coprime)
PYTHONPATH=. python apps/coprime.py 12 18    # -> 0 (not coprime, gcd=6)
```

### `is_prime.lova`

The first program here with an actual algorithm in it. Trial division
by recursion: walk a divisor upward until its square passes `n`.

```
(defn check [d n]
  (if-surprise (threshold (deviation (mul d d) n))
    1                                 ; d*d > n  -- no divisor, prime
    (if-surprise (mod n d)
      (check (merge d 1) n)           ; n mod d != 0  -- next d
      0)))                            ; d divides n   -- composite

(defn is-prime [n]
  (if-surprise (threshold (deviation 2 n)) 0 (check 2 n)))

(is-prime {n})
```

Run:

```
PYTHONPATH=. python apps/is_prime.py 97          # -> 1
PYTHONPATH=. python apps/is_prime.py 91          # -> 0 (7 x 13)
PYTHONPATH=. python apps/is_prime.py 561 1999    # Carmichael, then a prime
```

Note `(threshold (deviation a b))`: the core has no `<`. Ordering is
built from the surprise family — `deviation` is the signed sibling of
`surprise`, `threshold` is the sign test.

### `collatz.lova`

Counts Collatz steps to reach 1, carrying the counter as a second
curried parameter because LOVA has no mutable state and no pair type.

```
(defn next [n]
  (if-surprise (mod n 2) (merge (mul 3 n) 1) (partition n)))

(defn steps [n acc]
  (if-surprise (deviation n 1) (steps (next n) (merge acc 1)) acc))

(steps {n} 0)
```

Run:

```
PYTHONPATH=. python apps/collatz.py 27      # -> 111 steps
PYTHONPATH=. python apps/collatz.py 2463    # -> DepthTrap, not a crash
```

The second invocation is the point. Its trajectory is 208 steps, past
`MAX_CALL_DEPTH`, so the run ends in a structured anomaly naming the
limit, the overrun and what to do about it — the same schema as every
other LOVA trap. The Python equivalent raises `RecursionError` with a
stack trace an agent has to parse.

### `palindrome.lova`

The first program here that operates on **data** rather than on a
number.  Reverses a string and compares elementwise.

```
(def rev [xs acc]
  (if (nil? xs) acc (rev (tail xs) (cons (head xs) acc))))

(def same [a b]
  (if (nil? a) (nil? b)
    (if (nil? b) 0
      (if (dist (head a) (head b)) 0 (same (tail a) (tail b))))))

(def palindrome? [s] (same s (rev s (nil))))

(palindrome? {s})
```

Run:

```
PYTHONPATH=. python apps/palindrome.py racecar level abc
PYTHONPATH=. python apps/palindrome.py            # a default set
```

Three things it demonstrates:

- **A string is a list of codepoints.**  `"racecar"` is surface sugar
  for `(cons 114 (cons 97 ...))`, which is why the token table spends
  no slots at all on strings.
- **`dist` is `surprise`** — |a - b|, zero exactly when two codepoints
  match.  Equality never needed its own operator here.
- **The short spellings** (`if`, `dist`, `def`) are the one-token
  aliases Exp 13 measured: identical program, 30% fewer LLM tokens.

### `wordfreq.lova`

The M22 acceptance program: read a file under a declared boundary,
split it into words, count them in a map, sort, print the top n.  The
program that measured the interpreter's speed (journal M22, M23).

```
python -m core.cli run apps/wordfreq.lova notes.txt 10 --allow fs-read
```

### `tictactoe.lova`

Noughts and crosses against a memoised negamax.  The board is one
base-3 integer; the memo is a persistent map threaded through the
search as a value, because there is no other way to carry one.  You
are X; the computer never loses (20 random games under PyPy: 19 wins,
1 draw).  The argument is the board to start from, 0 for empty, so a
test can play an endgame instead of the first move's eleven-million-
step search.

```
python -m core.cli run apps/tictactoe.lova 0
printf '5\n1\n9\n' | python -m core.cli run apps/tictactoe.lova 0
```

### `guess.lova`

Guess the number.  The secret comes off the clock, under a boundary
the host has to grant; twelve lines, and two of the language's edges
found in writing them and closed the same day (Q78, Q79).

```
python -m core.cli run apps/guess.lova 100 --allow clock
```

### `logstats.lova`

A request log ("service status milliseconds" per line) summarised
per service: requests, mean and maximum latency, errors, most
requests first.  Read, parse, group in a map, aggregate, sort, print;
bad lines skipped.  Means are integers, because everything is.

```
python -m core.cli run apps/logstats.lova access.log --allow fs-read
```

### `ping.lova` / `pong.lova`

Two LOVA processes over UDP.  `pong` answers every datagram it
receives; `ping` sends k and prints the answers.  Each declares the
kind of effect (`net`); the host names the places:

```
python -m core.cli run apps/pong.lova 127.0.0.1:9002 --allow net=:9001,net=127.0.0.1:9002 &
python -m core.cli run apps/ping.lova 127.0.0.1:9001 3 --allow net=127.0.0.1:9001,net=:9002
```

### `sandbox.lova`

The agent scenario: untrusted programs, one per line of input, each
`read` into a value, run under a `budget`, and reported by hash and
value or by the name of its fault.  An infinite loop meets the
budget, a file read meets the boundary it did not declare, text that
is not a program is said to be one, and nothing reaches the sandbox,
which itself needs no grant.

```
python -m core.cli run apps/sandbox.lova 5000 < programs.txt
```

### `evolve.lova`

A function is a population (Axiom 6).  Five arithmetic programs are
seeded into a pool scored by distance from a target, evolved for k
generations with `lib/evolution.lova`, and the winner accounts for
itself from inside the language: its text, its value, its generation,
why it exists, how long its line of descent is.

```
python -m core.cli run apps/evolve.lova 42 60      # (mul (p 5) (tau 12)), distance 0
python -m core.cli run apps/evolve.lova 1000 200   # (merge (mul 33 30) 9) = 999
```

### `repair.lova`

Surprise is the debugger (Axiom 7).  A patient program violates a
`conserve` contract; the repairer mutates it, keeps a mutation only
if the surprise against the target shrinks, and stops at the first
version that satisfies the contract -- then prints the fix, the
attempts, its descent and its `why`.  Reproducible.

```
python -m core.cli run apps/repair.lova 42 30 200   # fixed in 39 attempts
```

### `batch.lova`

Conservation is declared in the program (Axiom 4).  300 Collatz jobs,
each under its own budget of nodes; the jobs that would cost more are
stopped, caught and counted, and the batch reports what finished.

```
python -m core.cli run apps/batch.lova 300 2000     # finished: 219, over budget: 81
```

### `shell/policy_app.py`

The division of labour LOVA is for, as a running application.  The
shell -- an HTTP server, a page, a form -- is ordinary Python, standard
library only.  The one thing that decides anything, a loyalty-points
rule, is a LOVA program you can edit in the browser.  The shell runs
it through the same call the MCP server exposes, under a budget of
50 000 nodes and with no capability granted, and shows what comes
back: the value, or the structured fault when you make the rule
divide by zero, loop for ever, read a file it never declared, or use a
name that does not exist.  The page also shows the rule as the integer
it is.  A shell in another language would call `lova mcp` and get the
same JSON.

```
python apps/shell/policy_app.py      # then open http://127.0.0.1:8765
```

![the policy console, a rule refused a file it never declared](shell/screenshot.png)

### `tanks.lova` / `tanks/tank_game.py`

Tank battle.  The rules are a library, `lib/tanks.lova`: the grid, the
walls, the player's and the enemies' moves, the bullets, the enemies'
aim, the spawning, the win and the loss -- about 250 lines, and not a
pixel or a key among them.  The world is one record and a turn is a
pure function of it: `(step w cmd)` gives the next world, `(render w)`
gives it as text, and the rules carry eighteen examples of themselves
that `lova check` runs.  Two hosts share the file.  `apps/tanks.lova`
is the terminal: one line a turn, `w d s a` to move, `f` to fire,
Enter to wait.  `apps/tanks/tank_game.py` is a window, tkinter and
nothing else: ten times a second it hands the LOVA program the world
and the key you are holding, gets the next world back and paints it,
and shows in the corner what the turn cost in steps -- about 10 000,
under a budget of 200 000, so a rule that ran away would be a
structured anomaly on the screen rather than a frozen window.  Eight
enemies, three at a time, wandering until they see you or the base
down a clear line; arrows or `wasd` move, space fires, `R` is another
game.

```
python -m core.cli run apps/tanks.lova 7            # the terminal, turn by turn
python -m core.cli check apps/tanks.lova 7          # 18/18 examples pass
python apps/tanks/tank_game.py                      # the window, in real time
```

![tank battle in a window; the window is Python, every rule is LOVA](tanks/screenshot.png)

### `maze.lova` / `maze/maze3d.py`

A first-person 3D maze, cast in fixed-point integers.  The rules are
`lib/ray.lova`: the maze, where you stand, which way you face, where
each ray stops, how tall that wall stands on the screen, which orb is
in front of which wall, whether the door opens.  LOVA has no floating
point, so lengths are in 1024ths of a cell and angles in 256ths of a
turn; a sine is a lookup in a 65-entry table and the perspective is
one `div`.  `lib/fixed.lova` holds that arithmetic on its own, because
`apps/cube.lova` needs it too.

The picture is `(frame w sw sh)`, and it knows nothing about pixels or
characters: a list of `sw` columns -- each a height in screen units, a
wall glyph, which face of it you see, and how far away it is -- plus
the orbs, one record a column, the far ones first, each already tested
against the wall in front of it and given its round edge by `isqrt`.
Two hosts draw it.  `apps/maze.lova` is the terminal: a line of moves
a turn, the view in characters with a plan of the maze beside it.
`apps/maze/maze3d.py` is a window, tkinter and nothing else, eight
times a second, with what the frame cost in steps in the corner --
about 35 000 under a budget of two million.

Six orbs are scattered about; carry all six to the door in the
south-east and it opens.

```
python apps/maze/maze3d.py                  # W/S walk, A/D turn, Q/E sidestep, R restarts
python -m core.cli run apps/maze.lova 0     # the terminal: wwd is three moves and a turn
python -m core.cli check apps/maze.lova 0   # the examples in the library
```

![a first-person maze; the window is Python, the 3D is LOVA](maze/screenshot.png)

### `cube.lova`

The other kind of 3D, and the one that had to be said out loud: eight
corners with three coordinates each, turned about two axes, moved away
from the camera and divided by their depth.  Nothing in it is special
to a grid -- it is the ordinary pipeline, in integers, on the same
`lib/fixed.lova` the raycaster uses.  Enter turns it a step, a digit
turns it that many, `q` stops; the nearest edge is written `@` and the
furthest `.`, which is the only depth cue a terminal gives.

```
python -m core.cli run apps/cube.lova
```

### `war/war.py`

The other camera: an isometric battlefield, the one an RTS looks
through.  `lib/war.lova` holds all of it -- a height field from value
noise read off a hashed lattice, an island falloff, water at sea
level, sand, grass, upland, rock and snow chosen by height and slope,
a sun dotted against each cell's normal over its own length for the
light, woods and boulders where the ground is flat enough, and then
twelve soldiers who walk, slide along a coast they cannot cross,
fight what comes within reach and die of it.

The ground is asked for once -- 1 296 cells, 2.5 million steps -- and
never again: the camera does not turn, so panning an isometric
projection is a translation, and the host draws the cells into a
scrolling canvas in the order LOVA hands them over, which is far ones
first because a painter has no depth buffer.  A tick of the battle is
about 6 000 steps.

Left-click picks one of your soldiers, drag pans the map, right-click
sends the ones you have picked, `A` takes all of them, `R` starts the
battle again.  The red side comes looking for you whatever you do.

```
python apps/war/war.py
```

![an isometric battlefield; the window is Python, the terrain, the light and the battle are LOVA](war/screenshot.png)

### `g2048.lova` / `g2048/game2048.py`

**A port, not a program of ours.**  2048, after
[gabrielecirulli/2048](https://github.com/gabrielecirulli/2048) (MIT),
whose `js/game_manager.js` and `js/grid.js` are the specification:
`lib/g2048.lova` follows the same traversal order, the same
farthest-position walk, the same rule that a tile made this move cannot
merge again, the same score, the same nine-in-ten chance of a two, the
same test for whether a move is left.  None of the original's code is
copied; the port was written against its behaviour.

The claim a port has to make is that it behaves like the thing it was
ported from, and prose is not how to make it: `tests/test_2048.py`
holds a transliteration of `GameManager.prototype.move` in Python and
runs both over random positions, comparing the board cell by cell, the
score, whether anything moved and whether 2048 appeared.  **10 000
positions, no disagreement**; 800 of them stay in the suite.

One difference on purpose.  The original's chance is `Math.random`, so
a game cannot be replayed; here the generator is threaded through the
world, so a seed is a game and the same seed is the same game twice.

The port also found a real bug in our own compiler: `drop-unused`
decided liveness first and then kept bindings whose value has effects,
so a constant kept that way outlived the function it called and the run
met an unbound reference.  Bindings kept for their effects now seed the
fixpoint (`core/compiler.py`).

```
python apps/g2048/game2048.py 7          # the window, in the original's colours
python -m core.cli run apps/g2048.lova 7 # the terminal: w a s d, several to a line
python -m core.cli check apps/g2048.lova 7   # 11/11 examples
```

![2048; the window is Python, the rules are LOVA](g2048/screenshot.png)

### `tactics/tactics.py`

**The second port, and the first from a game engine.**  The rules of
[ramaureirac/godot-tactical-rpg](https://github.com/ramaureirac/godot-tactical-rpg)
(MIT, ~960 stars), a Final-Fantasy-Tactics-shaped demo for Godot 4,
rewritten as `lib/tactics.lova` against its GDScript:

- `process_surrounding_tiles` -- a breadth-first flood from the tile a
  pawn stands on, one step a tile, across the four neighbours whose
  height is within its jump
- `mark_reachable_tiles` -- `0 < distance <= movement` and nobody
  standing there; `mark_attackable_tiles` -- `0 < distance <= range`
- damage is `stats.apply_to_curr_health(-attack_power)`: the attacker's
  power and nothing else, no height bonus, no facing, no roll
- the opponent is `choose_pawn` then `chase_nearest_enemy` then
  `choose_pawn_to_attack`: the first of its own that can still act, the
  tile beside the nearest of yours walked back until it can reach it,
  and then the weakest thing in range
- `Stats`: movement 3, `jump = floor(movement / 2)`, 5 health, reach 1,
  power 1

What a click *means* is decided in LOVA too, because it is a rule.

**The arena and the cast are the original's as well.**  Its
`test_arena.tscn` holds no model -- every "mesh" in that file is a
one-by-one quad, the top face of a tile, with the height in the node's
own transform -- so what there was to take was the layout, and it was
taken: two hundred tiles on ten by twenty, heights in eighths of a tile
because its ramps go down to an eighth.  The seven character sprites
are in `apps/tactics/assets/` under the original's MIT licence, which
travels with them; each is a 128 x 256 sheet of two frames and the
lower one faces the camera.  Delete them and the app draws figures of
its own instead.  The renderer is ours: Godot draws with a GPU, this is
isometric blocks a host paints from a list, far ones first.

Two places where the original contradicts itself are called out in the
header of `lib/tactics.lova` rather than quietly copied or quietly
fixed: it passes `movement` where its own flood wants a height, and an
`elif` that reads backwards lets *you* walk through an occupied tile
while refusing the opponent the same.  `tests/test_tactics.py` holds a
transliteration of the original's flood and compares the distance to
every cell of the arena for every kind of pawn.

The battle costs about 40 000 LOVA steps a picture, 130 000 with a pawn
picked up (the flood), and a few thousand for a click.

```
python apps/tactics/tactics.py   # click one of yours, space ends the turn, R again
```

![a tactics battle on blocks; the window is Python, the rules are LOVA](tactics/screenshot.png)

### `model/model.py`

The third camera in this repository, and the general one.  `ray.lova`
casts a ray a column through a grid; `tactics.lova` drops blocks on an
isometric plan; `lib/mesh3d.lova` takes a mesh of triangles with no
grid under it, turns it about two axes, divides it by its depth, throws
away the faces whose backs are turned, lights the rest and hands them
over far face first -- because a host painting polygons has no depth
buffer, and the order it is given is the whole of the depth sorting.

Two things make it cheap enough to run:

- **A face carries the normal it was born with.**  A rotation does not
  change a length, so a unit normal stays one however the model turns:
  a frame needs no square root anywhere.
- **The sun is carried into the model's frame once a frame**, instead
  of every normal being carried into the camera's.  A dot product does
  not care which frame it is taken in, and that turned a 45-step face
  into a 10-step one.

Culling is done on the screen: the sign of the projected triangle's
area, which is exact under perspective where a test on the normal is
only nearly right.  Two thirds of a closed model fail it and cost
nothing after it.

**What it costs**, over forty frames each: 32 triangles in 16 ms (61
frames a second), 48 in 25 ms (40), 66 in 31 ms (32), and the
320-triangle sphere in 139 ms (7).  About 220 LOVA steps a triangle,
and the step count is what the frame time follows.
**What it is worth**: `tests/test_mesh3d.py` holds the same renderer in
floating point and compares them face by face over five models and five
angles -- 961 faces, and **the fixed-point picture is within 1.34
pixels of the floating-point one**, with the same faces surviving the
cull and the same light on each.  The exception is named rather than
hidden: a triangle seen edge-on is a sliver a pixel wide, and rounding
its corners can turn it over.

```
python apps/model/model.py            # 1-5 pick a model, drag to turn, W wireframe
python apps/model/make_models.py      # rewrite lib/models.lova
python apps/model/obj_to_lova.py mine.obj lib/mine.lova mine
```

![a low-poly tree, turning; the window is Python, the 3D is LOVA](model/screenshot.png)

The five shipped meshes are generated out of boxes, cones, prisms and a
twice-subdivided icosahedron, so none of it is anybody else's art.
`obj_to_lova.py` reads a Wavefront `.obj` -- what Blender's exporter
writes -- and produces the same format.

### `fleet.lova`

**The policy layer of a fleet manager.**  Taken from RemoteX
(`D:/SSH/RemoteX`), an AI-native SSH fleet manager: a PyQt5 desktop, a
web terminal and an MCP server of 38 tools that Claude Code drives.
Its transport is `ssh2` and `paramiko`, its terminal is xterm.js, its
GUI is Qt -- none of which belongs in LOVA.  What does is what decides,
and `lib/fleet.lova` is two pieces of that.

**Ported exactly**, and checked against a transliteration of the
JavaScript in `tests/test_fleet.py`:

- `resolveActiveToolNames` -- which of the 38 tools a session
  advertises.  Every advertised tool costs context on every turn, so
  RemoteX ships five by default and prints the saving.  140 combinations
  of `REMOTEX_TOOLS` and `REMOTEX_TOOL_GROUPS` agree, including the
  banner's `Math.round((1 - active/total) * 100)`.
- `healthCheck`'s parse -- `stdout.split(/___(\w+)___/).filter(Boolean)`
  and the pairing loop.  The regular expression is greedy and `_` is a
  word character, so a marker is the *longest* run of word characters
  with `___` after it; `lib/fleet.lova` reproduces that by hand and
  agrees with Python's own engine (`re.ASCII`, because JavaScript's
  `\w` is ASCII and Python's is not) over thousands of strings built to
  break it.

**What was not there: the judgement.**  `healthCheck` returns five
strings and stops -- what counts as unhealthy lives in the model's head,
one machine at a time.  That is fine for one machine and no use for two
hundred.  `verdict` and `fleet-report` are thresholds in one place, a
per-machine level (ok / warn / alarm / nothing came back) and a fleet
sorted worst first.  11 100 LOVA steps a machine.

```
lova run apps/fleet.lova apps/fleet/sweep.txt --allow fs-read
```

```
  ?    ngin-edge2      cpu     --  mem     --  disk     --  load     --
ALARM  smapp3          cpu   99.4  mem   31.3  disk   28.0  load  17.40  up 29 days
ALARM  vas-cloud1      cpu    7.3  mem   23.9  disk   92.0  load   1.87  up 8 days
 warn  co3s-sedu5      cpu   35.1  mem   94.8  disk   22.0  load   1.96  up 25 days
   ok  smapp1          cpu   19.6  mem   31.0  disk   35.0  load   0.43  up 1 days

  12 machines: 2 alarm, 3 warn, 6 ok, 1 silent
```

It connects to nothing.  The input is a *recorded* sweep, because a
policy that decides whether two hundred production servers are in
trouble should be testable without touching two hundred production
servers; the host that holds the sockets hands the same text to the
same function.  `lib/fleet.lova` contains no boundary and no effect at
all -- a test asserts that -- and `apps/fleet.lova` declares `fs-read`,
which the host grants or the run does not happen.

## Arguments

A `{placeholder}` is filled from the command line in the order of
its first appearance in the code, or by name:

```
python -m core.cli run apps/batch.lova 300 2000
python -m core.cli run apps/batch.lova cost=2000 jobs=300
```

The newer programs declare their arguments first, so the order is
visible at the top of the file:

```
(def jobs [] {jobs})
(def cost [] {cost})
```

## Why these particular programs?

`is_perfect` and `coprime` use the four pieces that make LOVA actually
LOVA:

- **`let` / `ref`** — input binding (shows scope).
- **`merge`, `sigma`, `gcd`** — number-theoretic primitives as
  substrate operators.
- **`surprise`** — used as an *equality predicate* rather than a
  debugger.  The substrate records the comparison as a surprise
  event; the AI observer sees *why* the program decided.
- **`if-surprise`** — branching based on the surprise magnitude.

`is_perfect` in particular is **LOVA-idiomatic**: rather than
`if sigma(n) == 2*n`, it says *"hypothesise perfection; see how
surprised we are"*.  Identical outcome, different cognitive frame —
and the surprise trace is available to any AI post-hoc inspector.

## What's missing (so you know what these programs cannot do yet)

The list this section used to carry -- no output, no lists of lists,
no modules, no provenance from inside -- landed between M11 and M18.
What the twelve programs found in M23, and what became of it:

- **`stdin` keeps the line's terminator** (Q78, closed).  A blank
  line is `(10)`; only the end of the input is `nil`; `chomp` strips
  the newline when a program wants it gone.
- **`(def f [] body)` is a constant, not a thunk** (Q79, closed as a
  check).  It is evaluated once, where it is defined, so a recursive
  reference inside it is refused at compile time, by name.  A
  function that takes nothing has to take a dummy argument.
- **A boundary is lexical, and a region** (Q86, closed in M26).  A
  helper that uses an effect is written inside the boundary that
  declares it: `(boundary "clock" (def secret [n] ...) body)`.  The
  compiler still refuses an undeclared use before the run.
- **Records** (Q84, closed in M24): `(rec score s move k memo m)`
  and `(get st memo)` replaced the three-element lists
  `tictactoe.lova`'s search used to take apart by position.
- **Text is a value** (Q85, closed in M25): `words`, `split`, `join`
  and the rest are one operator each; the word count of 10 000 lines
  runs in 5.5 s on CPython where it took 28.
- **Speed.**  Solving the game is eleven million steps: 18 s on
  CPython, 3 s under PyPy.
- **`hash` is the program's integer, not a digest** (Q80, closed):
  150 digits for a program holding a short string.  `(digest p)` folds
  it to eighteen; `sandbox.lova` reports by it.
- **Arguments** (Q81, closed): `name=value` on the command line fills
  the placeholder it names, in any order.
- **`net-recv` yields the payload alone** (Q72): a server answers to
  an address it was given, not to whoever wrote.  Since M23 a send
  goes out from the listening socket when one is granted, so the peer
  at least sees a port to answer to.

`collatz.lova` still threads its counter through a curried parameter
rather than a pair -- worth rewriting now that a cons cell is a pair.

These are the first programs; they are intentionally narrow.  As
the language grows, the programs here will grow with it.
