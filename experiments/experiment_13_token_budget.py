"""Experiment 13 -- Re-deriving the 64-slot token budget.

Exp 12 left two facts sitting next to each other.  First, the density
claim reverses on algorithmic tasks: the Stage-1 surface costs 1.5x
more LLM tokens than Python where neither side has a built-in
shortcut.  Second, the slot budget is nearly spent -- of 39 reserved
operators, 24 belong to families already promised to Evolution, IO and
Meta, leaving **14 genuinely free slots**, while a minimal list type
plus `div` plus a comparison operator would consume 11-13 of them.

So the table has to be re-derived before anything else is built, and
the question is not "which operators would be nice" but "what does the
current allocation cost, and what would each candidate buy".  Four
parts:

  1. **Slot census.**  Which operators does existing LOVA code
     actually use, across three corpora?  LOVABench v2 (60 tasks),
     Exp 12's algorithmic set (10 tasks), and `apps/` (4 programs).
     The three disagree, and the disagreement is the finding: the
     benchmark was authored *in* the language, so it can only
     exercise what the language had.

  2. **Where the tokens go.**  Decompose the Stage-1 LLM-token cost
     into operator names, parentheses, literals and brackets.  This
     bounds what any change to the *table* can buy, because a token
     spent on a paren is not a token a new operator can reclaim.

  3. **Three levers, measured separately.**  Surface aliases cost
     zero slots; new primitives cost slots; a paren-free projection
     costs neither but changes the surface.  Conflating them is how a
     project talks itself into spending slots on a problem that was
     lexical.

  4. **Allocation ledger.**  What the 14 free slots can hold, what
     reallocating the number-theory family would add, and what Axiom 8
     should say afterwards.

Part 3's alias lever is *executed*: the aliases are registered, the
programs re-parsed and re-evaluated, and the results compared, so the
saving is measured on running code.  The new-primitive lever cannot
be executed -- the primitives do not exist -- so it is measured as a
mechanical contraction of the surface plus an analytic node-count
delta, and labelled as such.
"""

from __future__ import annotations

import collections
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import ALIASES, LIT_INT, SIGNATURES, TYPED_TOKENS, encode

try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # noqa: BLE001
    ENC = None


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _ntok(text: str) -> int:
    return len(ENC.encode(text)) if ENC is not None else 0


FAMILIES = [
    ("Structural", 0x00, 0x07),
    ("NumberTheory", 0x08, 0x0F),
    ("Conservation", 0x10, 0x17),
    ("Surprise", 0x18, 0x1F),
    ("Evolution", 0x20, 0x27),
    ("Composition", 0x28, 0x2F),
    ("Effects/IO", 0x30, 0x37),
    ("Meta/lineage", 0x38, 0x3F),
]

# Families whose reserved slots are already committed to a named future
# purpose.  Their slots are not available for reallocation without
# abandoning an axiom, so they are excluded from the "free" count.
COMMITTED = {"Evolution", "Effects/IO", "Meta/lineage"}


# --- corpora -----------------------------------------------------------------

def _bench_sources():
    from corpus.tasks import TASKS
    for task in TASKS:
        # Substitute a harmless concrete value for every {var} placeholder.
        yield task.id, re.sub(r"\{(\w+)\}", "7", task.template)


def _algorithmic_sources():
    from experiments.experiment_12_abstraction import TASKS as A_TASKS, _instantiate
    for task in A_TASKS:
        yield task.id, _instantiate(task, task.inputs[0])


def _app_sources():
    apps = os.path.join(_ROOT, "apps")
    for name in sorted(os.listdir(apps)):
        if not name.endswith(".lova"):
            continue
        with open(os.path.join(apps, name), encoding="utf-8") as handle:
            text = handle.read()
        # Apps carry {n} / {a} / {b} placeholders the driver substitutes.
        yield name, re.sub(r"\{(\w+)\}", "7", text)


CORPORA = [
    ("LOVABench v2", _bench_sources, "authored in the language, pre-M9"),
    ("algorithmic (Exp 12)", _algorithmic_sources, "recursion / iteration"),
    ("apps/", _app_sources, "programs written to do something"),
]


# --- part 1: slot census -----------------------------------------------------

def _count_ops(source: str, counter: collections.Counter) -> None:
    def walk(node):
        counter[node.op] += 1
        if node.op != LIT_INT:
            for arg in node.args:
                walk(arg)
    walk(parse(source))


def part_1_census() -> dict:
    _hr("1. Slot census -- what does existing LOVA code actually use?")

    counts = {}
    for label, source_fn, _note in CORPORA:
        counter = collections.Counter()
        n = 0
        for _ident, src in source_fn():
            _count_ops(src, counter)
            n += 1
        counts[label] = (counter, n)

    print(f"  {'operator':<16s} " + "".join(f"{label:>22s}" for label, _, _ in CORPORA))
    print("  " + "-" * 74)
    all_ops = sorted(set().union(*(c.keys() for c, _ in counts.values())))
    for op in all_ops:
        row = f"  0x{op:02X} {SIGNATURES[op]['name']:<11s} "
        for label, _, _ in CORPORA:
            counter, _ = counts[label]
            row += f"{counter.get(op, 0):>22d}"
        print(row)
    print("  " + "-" * 74)
    for label, _, note in CORPORA:
        counter, n = counts[label]
        print(f"  {label:<22s} {n:>3d} programs, "
              f"{len(counter):>2d} distinct operators used   ({note})")

    # The number-theory family is the interesting one: it holds 8 of 64
    # slots, and the three corpora disagree sharply about their worth.
    nt_ops = [op for op in range(0x08, 0x10) if op in TYPED_TOKENS]
    print()
    print("  Number-theory family (0x08-0x0F), 8 of 64 slots:")
    for label, _, _ in CORPORA:
        counter, _ = counts[label]
        nt_use = sum(counter.get(op, 0) for op in nt_ops)
        total = sum(counter.values())
        share = (nt_use / total * 100) if total else 0.0
        print(f"    {label:<22s} {nt_use:>4d} uses  ({share:.0f}% of all operator uses)")

    # Dead slots: implemented but never used anywhere.
    used_anywhere = set().union(*(c.keys() for c, _ in counts.values()))
    dead = sorted(set(TYPED_TOKENS) - used_anywhere)
    print()
    print(f"  Implemented but unused across all three corpora: "
          f"{[SIGNATURES[op]['name'] for op in dead] or 'none'}")

    # Free-slot accounting.
    print()
    print(f"  {'family':<14s} {'impl':>5s} {'reserved':>9s} {'free?':>7s}")
    print("  " + "-" * 40)
    free = []
    for name, lo, hi in FAMILIES:
        impl = [t for t in range(lo, hi + 1) if t in TYPED_TOKENS]
        res = [t for t in range(lo, hi + 1) if t not in TYPED_TOKENS]
        available = [] if name in COMMITTED else [t for t in res if t != 0x00]
        free += available
        print(f"  {name:<14s} {len(impl):>5d} {len(res):>9d} {len(available):>7d}")
    print("  " + "-" * 40)
    print(f"  {'TOTAL':<14s} {len(TYPED_TOKENS):>5d} "
          f"{64 - len(TYPED_TOKENS):>9d} {len(free):>7d}")
    print(f"  free slots: {[SIGNATURES[t]['name'] for t in free]}")
    return {"counts": counts, "free": free, "dead": dead}


# --- part 2: where the tokens go ---------------------------------------------

_PAREN_CHARS = set("() \n\t")
_BRACKET_CHARS = set("[] \n\t")


def _classify(piece: str) -> str:
    stripped = piece.strip()
    if not stripped:
        return "whitespace"
    if set(piece) <= _PAREN_CHARS:
        return "parens"
    if set(piece) <= _BRACKET_CHARS:
        return "brackets"
    if stripped.lstrip("-").isdigit():
        return "literals"
    return "names"


def _decompose(sources) -> collections.Counter:
    cat = collections.Counter()
    for _ident, src in sources:
        # Comments are not part of the program an LLM would emit.
        body = re.sub(r";[^\n]*", "", src)
        body = re.sub(r"\s+", " ", body).strip()
        for token in ENC.encode(body):
            cat[_classify(ENC.decode([token]))] += 1
    return cat


def part_2_where_tokens_go() -> dict:
    _hr("2. Where the Stage-1 tokens go")
    if ENC is None:
        print("  tiktoken not installed -- skipping "
              "(pip install -e \".[experiments]\")")
        return {}

    out = {}
    print(f"  {'corpus':<22s} {'total':>7s} {'names':>8s} {'parens':>8s}"
          f" {'literals':>9s} {'brackets':>9s} {'space':>7s}")
    print("  " + "-" * 74)
    for label, source_fn, _note in CORPORA:
        cat = _decompose(source_fn())
        total = sum(cat.values())
        out[label] = cat
        print(f"  {label:<22s} {total:>7d} "
              f"{cat['names']:>8d} {cat['parens']:>8d} "
              f"{cat['literals']:>9d} {cat['brackets']:>9d} "
              f"{cat['whitespace']:>7d}")
    print()
    algo = out["algorithmic (Exp 12)"]
    total = sum(algo.values())
    print(f"  On the algorithmic corpus, operator names and identifiers are")
    print(f"  {algo['names'] / total:.0%} of the cost and parentheses "
          f"{algo['parens'] / total:.0%}.")
    print("  A new operator can only ever reclaim tokens from the *names*")
    print("  share, and only where it removes nesting.  The paren share is")
    print("  a property of s-expressions, not of the table.")

    # Which operator names are expensive to spell?
    print()
    print("  operator names costing more than one tiktoken token:")
    for op in sorted(TYPED_TOKENS):
        name = SIGNATURES[op]["name"]
        cost = _ntok(name)
        if cost > 1:
            print(f"    0x{op:02X} {name:<16s} {cost} tokens")
    return out


# --- part 3: three levers ----------------------------------------------------

# Lever 1 -- surface aliases.  Zero slots, zero semantics: a second
# spelling for an operator that already exists.  Every alias below is a
# single tiktoken token; the canonical names stay canonical.
SHORT_ALIASES = {
    "if": "if-surprise",       # 3 tokens -> 1
    "dev": "deviation",        # 2 -> 1
    "tr": "trace-surprise",    # 3 -> 1
    "loop": "loop-until",      # 3 -> 1
    "keep": "conserve",        # 2 -> 1
    "dist": "surprise",        # 2 -> 1
    "mu": "mobius",            # 2 -> 1
    "def": "defn",             # 2 -> 1  (surface form, not an operator)
}

# `div` is not a contraction of an idiom -- it replaces a whole
# user-defined recursive function, so it is measured separately.
DIV_TASK_ID = "divide-by-subtracting"


# Lever 2 -- new primitives.  Costed here as one slot each; M10 took them
# as *macros* instead, on this experiment's own evidence -- 9% of the gap
# is a bad price for two slots when the same expansion is free.  The
# measurement is unchanged, because a macro and an operator cost the same
# number of surface tokens; what differs is the node count (2%) and the
# slot budget (2 slots).
#
# The rewrite has to happen on the **sugared source text**, because the
# sugared text is what an LLM emits and therefore what density means.
# Rewriting the AST instead would measure the desugared form, which is
# ~65% longer and not what anybody types.  And it has to be
# paren-aware: an earlier version of this experiment used a regex with
# `[^()]+?` argument groups, which cannot match a nested argument and
# silently under-counted `lt` by a factor of five.
NEW_PRIMITIVES = [
    ("lt", 1, "ordering; today (threshold (deviation b a))"),
    ("sub", 1, "subtraction; today (merge a (mul -1 b)) or (merge a -k)"),
]

# The slot count this experiment measured against, recorded so a re-run
# reproduces the reported ledger rather than silently reflecting whatever
# has been spent since.  M10 spent 6 of these 14.
FREE_SLOTS_AT_PROPOSAL = 14


def _balanced(text: str, pos: int) -> int:
    """End index (exclusive) of the s-expression starting at ``pos``."""
    if text[pos] != "(":
        end = pos
        while end < len(text) and text[end] not in " ()":
            end += 1
        return end
    depth = 0
    for i in range(pos, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced source")


def _args_at(text: str, pos: int, count: int):
    """Read ``count`` whitespace-separated s-expressions starting at ``pos``."""
    args = []
    cursor = pos
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        end = _balanced(text, cursor)
        args.append(text[cursor:end])
        cursor = end
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return args, cursor


def _rewrite_calls(text: str, head: str, arity: int, build):
    """Replace every ``(head a b ...)`` using ``build(args) -> str or None``.

    Innermost-last: the scan restarts from the replacement, so nested
    occurrences of the same idiom all get rewritten.
    """
    needle = "(" + head
    out = text
    hits = 0
    cursor = 0
    while True:
        idx = out.find(needle, cursor)
        if idx < 0:
            return out, hits
        after = idx + len(needle)
        if after < len(out) and out[after] not in " (":
            cursor = idx + 1                      # a longer name, e.g. merge-x
            continue
        try:
            args, end = _args_at(out, after, arity)
        except (ValueError, IndexError):
            cursor = idx + 1
            continue
        if end >= len(out) or out[end] != ")":     # wrong arity at this site
            cursor = idx + 1
            continue
        replacement = build(args)
        if replacement is None:
            cursor = idx + 1
            continue
        out = out[:idx] + replacement + out[end + 1:]
        hits += 1
        cursor = idx


def _contract_source(text: str):
    """Apply the `lt` and `sub` contractions to sugared source text."""
    saved_nodes = 0

    def build_lt(args):
        inner = args[0]
        if not inner.startswith("(deviation "):
            return None
        dev_args, end = _args_at(inner, len("(deviation "), 2)
        if end >= len(inner) or inner[end] != ")":
            return None
        # (threshold (deviation a b))  ==  a > b  ==  (lt b a)
        return f"(lt {dev_args[1]} {dev_args[0]})"

    def build_sub(args):
        left, right = args
        if right.startswith("(mul -1 "):
            mul_args, end = _args_at(right, len("(mul -1 "), 1)
            if end < len(right) and right[end] == ")":
                return f"(sub {left} {mul_args[0]})"
            return None
        if right.startswith("-") and right[1:].isdigit():
            return f"(sub {left} {right[1:]})"
        return None

    text, n_lt = _rewrite_calls(text, "threshold", 1, build_lt)
    saved_nodes += n_lt          # threshold+deviation (2 nodes) -> lt (1)
    text, n_sub = _rewrite_calls(text, "merge", 2, build_sub)
    # (merge a (mul -1 b)) is 3 nodes + a literal -> (sub a b) is 1 node;
    # (merge a -k) is 2 nodes -> (sub a k) is 2 nodes, no structural change.
    return text, saved_nodes, n_lt, n_sub


def _apply_aliases(text: str) -> str:
    """Rewrite operator names to their one-token aliases, head positions only."""
    out = text
    for alias, canonical in SHORT_ALIASES.items():
        out = re.sub(rf"\((?:{re.escape(canonical)})(?=[\s)])", f"({alias}", out)
    return out


def part_3_levers() -> dict:
    _hr("3. Three levers -- what each one is worth, and what it costs")
    if ENC is None:
        print("  tiktoken not installed -- skipping")
        return {}

    from experiments.experiment_12_abstraction import TASKS as A_TASKS, _instantiate

    # Register the aliases so the rewritten programs really run.
    for alias, canonical in SHORT_ALIASES.items():
        ALIASES.setdefault(alias, canonical)

    totals = dict(base=0, alias=0, prim=0, python=0)
    nodes = dict(base=0, prim=0)
    verified = 0
    lt_hits = sub_hits = 0

    print(f"  {'task':<24s} {'base':>6s} {'+alias':>7s} {'+prims':>7s}"
          f" {'Python':>7s}   contractions")
    print("  " + "-" * 72)

    for task in A_TASKS:
        src = _instantiate(task, task.inputs[0])
        expected = evaluate(parse(src), Runtime())
        base_nodes = _count_nodes(parse(src))

        alias_src = _apply_aliases(src)
        # Executed, not assumed: the alias rewrite must be the same program.
        assert evaluate(parse(alias_src), Runtime()) == expected, task.id
        verified += 1

        # Contract on the canonical spelling, THEN alias -- the other order
        # renames `deviation` out from under the contraction and silently
        # reports zero hits.
        contracted, saved, n_lt, n_sub = _contract_source(src)
        prim_src = _apply_aliases(contracted)
        # M10 took `lt` and `sub` as macros rather than as token slots, so
        # this column is now executable too -- it was a projection when
        # this experiment first ran.
        assert evaluate(parse(prim_src), Runtime()) == expected, task.id
        lt_hits += n_lt
        sub_hits += n_sub

        row = dict(base=_ntok(src), alias=_ntok(alias_src),
                   prim=_ntok(prim_src), python=_ntok(task.py_src))
        for key, value in row.items():
            totals[key] += value
        nodes["base"] += base_nodes
        nodes["prim"] += base_nodes - saved

        print(f"  {task.id:<24s} {row['base']:>6d} {row['alias']:>7d}"
              f" {row['prim']:>7d} {row['python']:>7d}   "
              f"lt={n_lt} sub={n_sub}")

    print("  " + "-" * 72)
    print(f"  {'TOTAL':<24s} {totals['base']:>6d} {totals['alias']:>7d}"
          f" {totals['prim']:>7d} {totals['python']:>7d}   "
          f"lt={lt_hits} sub={sub_hits}")
    print()
    print(f"  every column re-parsed and re-evaluated: {verified}/{len(A_TASKS)}"
          " tasks, identical results")
    print("  (the `+prims` column was a projection when this experiment first")
    print("   ran; M10 shipped `lt` and `sub` as macros, so it now executes)")

    py = totals["python"]
    print()
    print(f"  {'lever':<38s} {'slots':>6s} {'tokens':>8s} {'vs Python':>11s}")
    print("  " + "-" * 66)
    print(f"  {'as shipped':<38s} {0:>6d} {totals['base']:>8d} "
          f"{py / totals['base']:>10.2f}x")
    print(f"  {'+ one-token operator aliases':<38s} {0:>6d} "
          f"{totals['alias']:>8d} {py / totals['alias']:>10.2f}x")
    slots = sum(n for _, n, _ in NEW_PRIMITIVES)
    print(f"  {'+ lt and sub (M10: macros, 0 slots)':<38s} {0:>6d} "
          f"{totals['prim']:>8d} {py / totals['prim']:>10.2f}x")
    print()
    print(f"  gap to parity closed by the free lever:  "
          f"{(totals['base'] - totals['alias']) / (totals['base'] - py):.0%}")
    print(f"  gap to parity closed by the 2 slots:     "
          f"{(totals['alias'] - totals['prim']) / (totals['base'] - py):.0%}")
    print()
    print("  node count (drives encoded bytes and the Stage-2 estimate):")
    print(f"    as shipped {nodes['base']} -> with lt+sub {nodes['prim']} "
          f"({(1 - nodes['prim'] / nodes['base']) * 100:.0f}% fewer)")

    div_task = next(t for t in A_TASKS if t.id == DIV_TASK_ID)
    div_src = _instantiate(div_task, div_task.inputs[0])
    print()
    print("  `div` is not an idiom contraction -- it deletes a definition:")
    print(f"    today:        {_ntok(div_src)} tokens, "
          f"{_count_nodes(parse(div_src))} nodes, O(a/b) recursion")
    print(f"    with a slot:  {_ntok('(div 10 2)')} tokens, 3 nodes, O(1)")
    print("    One task's density, but every future program that divides.")

    print()
    print("  Residual after every lever: parentheses and identifiers, which")
    print("  no change to the table can reclaim.  Closing the rest means a")
    print("  different surface (Stage 2), not different operators.")

    return {
        "baseline": totals["base"], "aliased": totals["alias"],
        "contracted": totals["prim"], "python": py, "slots_spent": slots,
        "base_nodes": nodes["base"], "contracted_nodes": nodes["prim"],
        "lt_hits": lt_hits, "sub_hits": sub_hits,
    }


def _count_nodes(node) -> int:
    if node.op == LIT_INT:
        return 1
    return 1 + sum(_count_nodes(c) for c in node.args)


# --- part 4: the ledger ------------------------------------------------------

# The proposal, ranked by the evidence above rather than by appeal.
#
# `slots` is what each line costs; `basis` says which measurement
# justifies it.  Lines are ordered by how badly the language needs them,
# which is not the same as how much density they buy -- and saying so is
# the point of keeping the two columns apart.
PROPOSAL = [
    ("nil, cons, head, tail, nil?", 5, "census",
     "one cons cell buys pairs AND lists AND strings-as-codepoint-lists; "
     "without it there is no two-value return and no collection at all"),
    ("div", 1, "complexity",
     "48 tokens and O(a/b) recursion per use become 6 tokens and O(1)"),
    ("quote, eval", 2, "axiom",
     "a program as a value -- required by Axiom 1 and by Stage 3's "
     "(explain program), neither of which is reachable today"),
    ("lt, sub", 2, "density",
     "measured: 9% of the algorithmic density gap, 5+7 sites in 10 tasks"),
]

# Deliberately NOT proposed, with the reason recorded so the decision is
# revisitable rather than forgotten.
REJECTED = [
    ("reallocate the number-theory family", 8,
     "the census says 3-5% use outside the benchmark, which looks damning "
     "until you notice the demand above fits in 14 slots without touching "
     "it; spend them only if strings-as-lists proves too slow"),
    ("a dedicated string type", "5-6",
     "unnecessary: a string is a list of codepoints once cons exists, and "
     "a \"abc\" surface literal is sugar, costing zero slots"),
    ("shorter operator names", 0,
     "not a slot decision at all -- it is the single largest measured "
     "density lever and it is free; see the Axiom 8 revision"),
]


def part_4_ledger(census: dict, levers: dict) -> None:
    _hr("4. Allocation ledger")
    free = census["free"]
    print(f"  free slots when this proposal was written: "
          f"{FREE_SLOTS_AT_PROPOSAL}")
    print(f"  free slots now:                            {len(free)}")
    print(f"    {[SIGNATURES[t]['name'] for t in free]}")
    if len(free) != FREE_SLOTS_AT_PROPOSAL:
        print(f"  ({FREE_SLOTS_AT_PROPOSAL - len(free)} spent since -- see the "
              "M10 record in journal/README.md; the rows below are the "
              "proposal as measured, not the current state)")
    print()
    print(f"  {'proposed':<30s} {'slots':>6s} {'basis':>11s}")
    print("  " + "-" * 74)
    demand = 0
    for name, slots, basis, why in PROPOSAL:
        demand += slots
        print(f"  {name:<30s} {slots:>6d} {basis:>11s}")
        print(f"  {'':<30s} {'':>6s} {'':>11s}  {why}")
    print("  " + "-" * 74)
    print(f"  {'TOTAL':<30s} {demand:>6d}   of "
          f"{FREE_SLOTS_AT_PROPOSAL} free -> "
          f"{FREE_SLOTS_AT_PROPOSAL - demand} slots headroom, deliberately "
          "unspent")
    print()
    print("  Not proposed:")
    for name, slots, why in REJECTED:
        print(f"    {name} ({slots} slots)")
        print(f"      {why}")

    if levers:
        print()
        print("  What each lever is actually worth, side by side:")
        print(f"    {'lever':<32s} {'slots':>6s} {'gap closed':>12s}")
        print("    " + "-" * 52)
        gap = levers["baseline"] - levers["python"]
        free_gain = levers["baseline"] - levers["aliased"]
        slot_gain = levers["aliased"] - levers["contracted"]
        print(f"    {'operator spelling (surface)':<32s} {0:>6d} "
              f"{free_gain / gap:>11.0%}")
        print(f"    {'lt + sub (new primitives)':<32s} {2:>6d} "
              f"{slot_gain / gap:>11.0%}")
        print(f"    {'residual: parens + identifiers':<32s} "
              f"{'n/a':>6s} {1 - (free_gain + slot_gain) / gap:>11.0%}")
        print()
        print("  The free lever is worth three times the two slots, and the")
        print("  residual is worth more than both together.  A table change")
        print("  is the wrong instrument for the density problem; it is the")
        print("  right instrument for the expressiveness problem.")


# --- main --------------------------------------------------------------------

def run() -> None:
    print("LOVA Experiment 13 -- re-deriving the 64-slot token budget")
    if ENC is None:
        print("  (tiktoken missing: parts 2 and 3 need it)")
    census = part_1_census()
    part_2_where_tokens_go()
    levers = part_3_levers()
    part_4_ledger(census, levers)

    _hr("Experiment 13 -- summary")
    if levers:
        print("  algorithmic density vs Python:")
        print(f"    as shipped                          "
              f"{levers['python'] / levers['baseline']:.2f}x")
        print(f"    + operator aliases   (0 slots)      "
              f"{levers['python'] / levers['aliased']:.2f}x")
        print(f"    + lt, sub            ({levers['slots_spent']} slots)      "
              f"{levers['python'] / levers['contracted']:.2f}x")
        print("    ...still below parity: the rest is s-expression syntax.")
    print()
    print(f"  number-theory family use: "
          + ", ".join(
              f"{label} {sum(c.get(op, 0) for op in range(0x08, 0x10))}"
              for label, (c, _n) in census["counts"].items()))
    print(f"  proposed spend: {sum(s for _, s, _, _ in PROPOSAL)} of "
          f"{FREE_SLOTS_AT_PROPOSAL} free slots at the time; "
          f"{len(census['free'])} free now")
    print(f"  implemented but unused in any corpus: "
          f"{[SIGNATURES[op]['name'] for op in census['dead']] or 'none'}")


if __name__ == "__main__":
    run()
