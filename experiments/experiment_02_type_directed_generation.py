"""Experiment 02 -- Type-directed generation (Axiom 3 validation).

The load-bearing claim of Axiom 3:

  From any prefix of a LOVA token sequence, the set of well-typed
  next tokens is computable.  An AI sampling only from this set
  produces programs that are, by construction, well-formed and
  well-typed.  Ill-typed programs are unreachable from any valid prefix.

This experiment demonstrates the claim quantitatively:

1. Walk through 5 concrete prefixes and show their valid_next sets --
   especially LET's "only LIT_INT" sharp constraint.
2. Generate N=1000 programs under ``constrained_random``; verify
   100% validate.
3. Generate N=1000 programs under ``unconstrained_random`` (pick any
   M1 token + random LIT_INT payload, no state check); measure
   fraction that accidentally validate.
4. Report the delta as evidence that type-directed generation is a
   load-bearing AI-friendly property, not a cosmetic feature.

Paradigm-lineage reminder (see ``spec/paradigm-inheritance.md``):
grammar-constrained decoding (Outlines/llguidance) + dependent-type
narrowing (Agda/Idris) + positional typing (Forth/APL) = LOVA's
substrate-level generation constraint.
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.generator import (
    GenState, constrained_random, unconstrained_random, validates,
)
from core.tokens import (
    END, GCD, IF_SURPRISE, LET, LIT_INT, MERGE, P, SEQ, SIGNATURES, TAU,
    decode,
)
from core.surface import pretty


# --- helpers ----------------------------------------------------------------

def _hr(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _show_valid(state: GenState, label: str) -> None:
    v = sorted(state.valid_next())
    if not v:
        print(f"  {label:<32s} |valid| = 0  (program complete)")
        return
    names = [SIGNATURES[t]["name"] if t in SIGNATURES else f"0x{t:02X}"
             for t in v]
    # truncate display if long
    disp = ", ".join(names) if len(names) <= 10 else \
        ", ".join(names[:8]) + f", ... (+{len(names)-8} more)"
    print(f"  {label:<32s} |valid| = {len(v):2d}  -> {disp}")


# --- Test 1: walk through concrete prefixes ---------------------------------

def test_concrete_prefixes() -> None:
    _hr("Test 1 -- concrete prefix walk (valid_next sharpness)")

    # Prefix 1: empty (starting to generate)
    s = GenState.fresh()
    _show_valid(s, "empty (start)")

    # Prefix 2: after picking GCD
    s = s.step(GCD)
    _show_valid(s, "GCD . (expecting Int)")

    # Prefix 3: after GCD + LIT_INT (payload handled implicitly in walk)
    s = s.step(LIT_INT)
    _show_valid(s, "GCD LIT . (expecting Int)")

    # Prefix 4: after LET (sharp constraint -- only LIT_INT)
    s2 = GenState.fresh().step(LET)
    _show_valid(s2, "LET . (name slot demands LiteralInt)")
    assert s2.valid_next() == frozenset({LIT_INT}), \
        "LET's first slot must admit ONLY LIT_INT"

    # Prefix 5: after LET + LIT_INT + LIT_INT, expecting body (Int)
    s3 = GenState.fresh().step(LET).step(LIT_INT).step(LIT_INT)
    _show_valid(s3, "LET LIT LIT . (body slot, any Int)")

    # Prefix 6: inside a SEQ variadic
    s4 = GenState.fresh().step(SEQ)
    _show_valid(s4, "SEQ . (variadic; END is valid here)")
    assert END in s4.valid_next(), "variadic slot must allow END as terminator"

    # Prefix 7: SEQ + one element; still variadic, still allow more or END
    s5 = s4.step(LIT_INT)
    _show_valid(s5, "SEQ LIT . (still variadic)")

    print()
    print("  findings:")
    print("    * fresh/top-level slot admits 18 tokens (all Int producers)")
    print("    * LET's name slot admits ONLY LIT_INT (sharp constraint)")
    print("    * variadic slots include END as a terminator option")


# --- Test 2: constrained generation is 100% well-typed ----------------------

def test_constrained_generation(n_samples: int = 1000) -> None:
    _hr(f"Test 2 -- constrained_random: {n_samples} samples, expect 100% valid")
    t0 = time.time()
    pass_count = 0
    total_bytes = 0
    samples_by_bytes: list = []
    for seed in range(n_samples):
        data = constrained_random(seed=seed, max_depth=6)
        total_bytes += len(data)
        if validates(data):
            pass_count += 1
        if seed < 5:
            samples_by_bytes.append(data)
    dt = time.time() - t0
    rate = pass_count / n_samples
    avg_bytes = total_bytes / n_samples
    print(f"  validated: {pass_count}/{n_samples}  ({rate*100:.1f}%)")
    print(f"  avg bytes: {avg_bytes:.1f}  "
          f"(generation time: {dt*1000:.0f}ms for {n_samples} programs)")
    print()
    print("  sample output (first 5 seeds):")
    for i, data in enumerate(samples_by_bytes):
        tree = decode(data)
        src = pretty(tree)
        print(f"    seed {i}: {data.hex(' ')[:40]:<40s} -> {src}")
    assert pass_count == n_samples, (
        f"constrained_random must be 100% valid, got {pass_count}/{n_samples}"
    )
    return rate


# --- Test 3: unconstrained generation fails mostly --------------------------

def test_unconstrained_generation(n_samples: int = 1000) -> float:
    _hr(f"Test 3 -- unconstrained_random: {n_samples} samples, expect << 100%")
    t0 = time.time()
    pass_count = 0
    for seed in range(n_samples):
        data = unconstrained_random(seed=seed, max_tokens=10)
        if validates(data):
            pass_count += 1
    dt = time.time() - t0
    rate = pass_count / n_samples
    print(f"  validated: {pass_count}/{n_samples}  ({rate*100:.2f}%)")
    print(f"  (generation time: {dt*1000:.0f}ms for {n_samples} programs)")
    print()
    print("  interpretation:")
    print("    * unconstrained generation is picking tokens without regard")
    print("      for the state machine -- arity / type / END-placement all")
    print("      violate frequently.  This is roughly what an unguided LLM")
    print("      token sampler produces if it's never seen LOVA training data.")
    return rate


# --- Test 4: the delta (the AI-friendly claim, quantified) ------------------

def test_delta(constrained_rate: float, unconstrained_rate: float) -> None:
    _hr("Test 4 -- the AI-friendly property, quantified")
    delta_abs = constrained_rate - unconstrained_rate
    ratio = (
        constrained_rate / max(unconstrained_rate, 1e-9)
        if unconstrained_rate > 0 else float("inf")
    )
    print(f"  constrained validate rate:    {constrained_rate*100:6.2f}%")
    print(f"  unconstrained validate rate:  {unconstrained_rate*100:6.2f}%")
    print(f"  delta (absolute):             {delta_abs*100:+6.2f} pp")
    print(f"  ratio (constrained / uncon.): {ratio:.1f}x")
    print()
    print("  claim (Axiom 3):")
    print("    A type-directed generator is, by construction, 100% valid.")
    print("    An unguided generator over the same token set is << 100%.")
    print("    The gap is load-bearing: this is the property that makes")
    print("    LOVA AI-friendly -- LLM samplers constrained to valid_next")
    print("    cannot emit ill-formed programs at all.")


# --- main -------------------------------------------------------------------

def run() -> None:
    test_concrete_prefixes()
    c_rate = test_constrained_generation(n_samples=1000)
    u_rate = test_unconstrained_generation(n_samples=1000)
    test_delta(c_rate, u_rate)

    _hr("Experiment 02 -- RESULT")
    if c_rate == 1.0 and u_rate < 0.5:
        print("  WIN.  Axiom 3 is operational: type-directed generation")
        print("  produces 100% well-typed programs; unguided generation")
        print(f"  produces only {u_rate*100:.1f}%.  Gap is load-bearing.")
    elif c_rate == 1.0:
        print("  PARTIAL.  Constrained is 100% but the gap to unguided is")
        print("  smaller than expected.  Investigate unguided baseline.")
    else:
        print("  NULL.  Constrained is not 100% -- generator has a bug.")


if __name__ == "__main__":
    run()
