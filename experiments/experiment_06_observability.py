"""Experiment 06 -- Observability (L1 + L2 + L3).

The AI-preference levers made concrete:

  L1. ``valid_next_with_stats``  -- per-token metadata at a generation
      position.  Given a partial program, for each valid next token,
      expose its arity / depth-delta / effects / cost / termination
      behavior.  AI sampling uses this as a structured signal rather
      than a flat set of bytes.

  L2. Enriched anomaly reports   -- when a conservation or budget trap
      fires, the exception carries structured fields (position_path,
      offending_op, valid_alternatives, repair_hint) instead of an
      English stack trace.  AI can pattern-match these to patch the
      program in one step.

  L3. ``static_analyze``         -- given a LOVA program, compute
      what it WILL do before running: effects, max cost, determinism,
      whether it uses conservation / surprise / lineage.  AI can ask
      "what are the consequences of running this" before committing
      to execute.

These three together change LOVA from "a language AI can use" to
"a language AI can REASON about".  This is the foundation for making
AI prefer LOVA over Python in its set of tools.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.conservation import BudgetTrap, DeltaTrap
from core.generator import GenState
from core.observability import (
    TokenChoice, static_analyze, suggest_alternatives, valid_next_with_stats,
)
from core.runtime import Runtime, evaluate
from core.surface import parse
from core.tokens import (
    BUDGET, CONSERVE, LET, LIT_INT, MERGE, P, SEQ, SIGNATURES, SURPRISE, TAU,
)


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


# --- L1 demo ----------------------------------------------------------------

def demo_l1_valid_next_with_stats() -> None:
    _hr("L1 -- valid_next_with_stats (per-token metadata for AI sampling)")

    # Three interesting prefixes:
    prefixes = [
        ("empty (fresh state)", GenState.fresh()),
        ("after LET -> name slot", GenState.fresh().step(LET)),
        ("after SEQ -> variadic", GenState.fresh().step(SEQ)),
        ("after MERGE, LIT -> 2nd arg slot",
         GenState.fresh().step(MERGE).step(LIT_INT)),
    ]

    for label, state in prefixes:
        print(f"\n  {label}  (stack depth {len(state.stack)})")
        choices = valid_next_with_stats(state)
        print(f"    |valid| = {len(choices):2d}")
        for c in choices:
            print(f"      {c.summary()}")

    print()
    print("  interpretation:")
    print("    * fresh/open slot:  18 choices, mix of expanding (depth+1)")
    print("      and one terminating (lit).  AI heuristic: near depth-")
    print("      budget, prefer terminating.")
    print("    * LET name slot:    1 choice only (lit).  Sharp constraint.")
    print("    * SEQ variadic:    19 choices incl. END (the terminator).")
    print("      Effects visible per-token: surprise / conserve / budget")
    print("      are flagged for AI's static reasoning.")


# --- L2 demo ----------------------------------------------------------------

def _pretty_anomaly(anom: dict) -> None:
    """Print the anomaly dict in a readable shape for the demo."""
    print(f"    kind:             {anom['kind']!r}")
    print(f"    detail:           {anom['detail']}")
    print(f"    position_path:    {anom['position_path']}  (opcode chain)")
    if anom['offending_op'] is not None:
        print(f"    offending_op:     0x{anom['offending_op']:02X} "
              f"({anom['offending_op_name']})")
    alts = anom['valid_alternatives']
    if alts:
        alt_names = [SIGNATURES[a]['name'] for a in alts]
        print(f"    valid_alts:       {alts}  ({alt_names})")
    else:
        print(f"    valid_alts:       (none)")
    print(f"    repair_hint:      {anom['repair_hint']}")


def demo_l2_enriched_traps() -> None:
    _hr("L2 -- enriched anomaly reports (machine-actionable)")

    # Scenario 1: BudgetTrap with deep program
    prog1 = parse("(budget 3 (merge (p 3) (tau 12)))")
    print()
    print("  Scenario A: budget exceeded on a 5-node body under budget=3")
    print(f"    program: {prog1}")
    try:
        evaluate(prog1)
    except BudgetTrap as t:
        print(f"    trap raised: {t}")
        print(f"    anomaly:")
        _pretty_anomaly(t.anomaly)

    # Scenario 2: DeltaTrap from violate
    prog2 = parse("(conserve 77 (violate 77))")
    print()
    print("  Scenario B: conservation violated (violate bumps value by +1)")
    print(f"    program: {prog2}")
    try:
        evaluate(prog2)
    except DeltaTrap as t:
        print(f"    trap raised: {t}")
        print(f"    anomaly:")
        _pretty_anomaly(t.anomaly)

    # Demo: AI-style repair using valid_alternatives
    print()
    print("  Demo -- AI repair flow using ``valid_alternatives``:")
    print("    AI reads scenario A's anomaly, sees offending_op=tau.")
    tau_alts = suggest_alternatives(0x09)
    alt_names = [SIGNATURES[a]['name'] for a in tau_alts]
    print(f"    suggest_alternatives(tau) = {tau_alts} ({alt_names})")
    print(f"    AI picks 'p' (byte 0x08) and retries with (budget 3 (merge (p 3) (p 12))).")
    print(f"    New program retains the same structure, same cost -- still")
    print(f"    fails budget (same count of nodes), but AI's next step is to")
    print(f"    either raise budget (repair_hint says >= 4) or shrink body.")


# --- L3 demo ----------------------------------------------------------------

def demo_l3_static_analyze() -> None:
    _hr("L3 -- static_analyze (pre-execution reasoning about programs)")

    programs = [
        ("pure integer computation",
         "(merge (p 12) (tau 100))"),
        ("uses conservation budget",
         "(budget 100 (merge (p 12) (sigma 12)))"),
        ("uses surprise primitive",
         "(if-surprise (surprise 10 (p 12)) 999 0)"),
        ("complex with let/ref",
         "(let 0 12 (merge (p (ref 0)) (sigma (ref 0))))"),
        ("mixes conservation + surprise",
         "(conserve 77 (surprise 77 (p 12)))"),
    ]
    for label, src in programs:
        print()
        print(f"  {label}")
        print(f"    program: {src}")
        tree = parse(src)
        analysis = static_analyze(tree)
        print(analysis.summary())

    print()
    print("  interpretation:")
    print("    AI can ask 'what will this program do' without running it.")
    print("    The 'effects' set tells AI whether the program touches")
    print("    the surprise trace, a conservation scope, or is pure.")
    print("    'uses_surprise=True' is a flag that says 'this program")
    print("    interacts with the debugger primitive'.  AI can gate on")
    print("    that before executing in a sensitive context.")


# --- L1 + L3 composite demo -------------------------------------------------

def demo_ai_guided_sampling() -> None:
    _hr("Composite -- AI-guided sampling using L1 stats")

    # Imagine an AI is generating a program and wants to STOP quickly
    # once stack depth gets above 4.  It uses termination-biased
    # sampling from valid_next_with_stats to steer toward terminal tokens.

    import random
    rng = random.Random(7)
    state = GenState.fresh()
    tokens_chosen = []
    path_log = []

    MAX_STEPS = 40
    for step in range(MAX_STEPS):
        if state.is_complete():
            break
        choices = valid_next_with_stats(state)
        depth = len(state.stack)
        # AI heuristic: if deep, pick terminating tokens; else pick any.
        if depth >= 3:
            terminating = [c for c in choices if c.terminating]
            candidates = terminating if terminating else choices
        else:
            candidates = choices
        choice = rng.choice(candidates)
        path_log.append((step, depth, choice.name, choice.terminating))
        if choice.token == LIT_INT:
            # Also emit a random small literal
            lit_val = rng.randint(0, 20)
            tokens_chosen.append((choice.token, lit_val))
        else:
            tokens_chosen.append((choice.token, None))
        state = state.step(choice.token)

    print()
    print("  Simulated AI generation with depth-aware termination bias:")
    print(f"    steps: {len(path_log)}")
    print(f"    sample path (depth / chosen / term?):")
    for step, depth, name, term in path_log:
        t_mark = "TERM" if term else "    "
        print(f"      step {step:2d}  depth={depth}  {t_mark}  {name}")

    # Construct the program bytes from tokens_chosen
    from core.generator import encode_lit
    from core.tokens import END, decode
    from core.surface import pretty
    out = bytearray()
    for tok, lit in tokens_chosen:
        out.append(tok)
        if tok == LIT_INT:
            out.extend(encode_lit(lit or 0))
    # Close variadics (add END for each remaining variadic on the stack)
    # Actually just check: state should be complete or nearly so
    print()
    if state.is_complete():
        tree = decode(bytes(out))
        print(f"    program: {pretty(tree)}")
        print(f"    bytes:   {len(out)}")
        try:
            result = evaluate(tree)
            print(f"    result:  {result}")
        except Exception as e:
            print(f"    eval:    {type(e).__name__}: {e}")
    else:
        print(f"    (generation incomplete after {MAX_STEPS} steps; "
              f"stack depth still {len(state.stack)})")


# --- main -------------------------------------------------------------------

def run() -> None:
    print("LOVA M5 -- Observability layer (L1 + L2 + L3)")
    print("Making the substrate's internal state readable to AI.")
    demo_l1_valid_next_with_stats()
    demo_l2_enriched_traps()
    demo_l3_static_analyze()
    demo_ai_guided_sampling()
    _hr("Experiment 06 -- complete")
    print("  L1 ship: valid_next_with_stats returns TokenChoice objects")
    print("    with arity / depth_delta / terminating / effects / cost.")
    print("  L2 ship: trap anomalies carry kind / detail / position_path /")
    print("    offending_op / valid_alternatives / repair_hint.")
    print("  L3 ship: static_analyze returns effects, budget bound,")
    print("    determinism, uses-of (conservation / surprise / lineage).")
    print()
    print("  Next: Exp 07 -- Claude-vs-Claude benchmark using these APIs")
    print("    as feedback signal.  Measures pass@1 delta with/without L1-L3.")


if __name__ == "__main__":
    run()
