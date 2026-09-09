# Experiment 16 — Scope-aware generation: Axiom 3 at the name level

**Date:** 2026-09-09
**Script:** `experiments/experiment_16_scope_generation.py`
**Status:** Done (N=1000 × 2 modes). **WIN.** Closes Q54; qualifies Axiom 3 upward.

## Hypothesis

Axiom 3 — ill-typed programs are not representable — held at the
operator level only, because the generation state machine never saw a
LIT_INT payload and so never knew which names were bound (Exp 12, F4).
If `step` is given the payload, the machine can keep scope, offer `ref`
only where a bound and type-compatible name exists, and make an unbound
reference unrepresentable rather than a compile error.

## Method

`GenState` gains frames: a LET or LAMBDA opens one, its binder's literal
names it, the binding's first token types it (unknown for calls and
parameters, as in the compiler), and the frame closes when the form's
subtree completes. `valid_next` offers `ref` only if some frame fits
the slot; `literal_for` gives a sampler a fresh name for a binder and a
bound one for a ref. `track_scope=False` reproduces the old machine.

1000 programs per mode, same seeds, classified by the compiler's scope
pass and a bounded run.

## Results

| Outcome (N=1000) | pre-M16 | M16 |
|---|---|---|
| unbound reference | **704 (70%)** | **0** |
| other compile error | 47 | 1 |
| compiles, traps at run time | 93 | 629 |
| compiles and runs | **156 (16%)** | **370 (37%)** |
| references emitted | 1306 | 122 |
| `apply` head is a reference | 74 | 5 |
| `apply` head is a lambda / loop-until | 62 | 110 |

*Re-run at M17*, after the termination bias was restricted to certain
closers (so the old machine's bias no longer reaches for `ref` either):
pre-M16 unbound **248**, runnable **291**; M16 unbound **0**, runnable
**379**. The baseline moved because the bias moved; the M16 column did
not change in kind. `experiments/results_16/run.log` holds the M17
numbers.

Boundary: self recursion, nested lets and shadowing validate; a
**mutually recursive `def` chain compiles (M12) but does not validate**.

Exp 10, whose samplers now emit real names: weighted vs uniform
**88% vs 56%, +32 pp** (was +40 pp at M13, +20 pp in April).

## Findings

**F1. Seventy percent of generated programs were referencing nothing.**
That is the number behind Exp 08's "unbound-ref moved to compile time"
and Exp 10's pass rates: most of what the sampler produced was dead on
arrival for a reason the state machine could have prevented and did
not. It now produces none.

**F2. Runnable programs more than doubled — and the trap rate is now
the frontier.** 16% → 37% compile and run. The 63% that compile and
trap were mostly invisible before, hidden behind the unbound-ref
rejection. Division by zero, `head` of the empty list, budget overruns:
the semantic layer Axiom 3 always said errors would move to. They have.

**F3. Q54 closes by construction.** An `Fn` slot is filled by a
reference only when a bound function fits (74 → 5, and those 5 are
bound). Otherwise `ref` is not offered and the depth bias reaches for
`lambda`. The 1306 → 122 drop in references is the same fact: a
reference now costs a binding.

**F4. Generation is strictly more conservative than the compiler, and
that is the right direction.** A left-to-right machine cannot emit a
reference to a name bound later, so mutual recursion — legal since M12
— is compilable but not generatable. Everything the generator emits
compiles; not everything that compiles can be generated. The compiler
keeps its scope pass for the trees that do not come from the generator:
hand-written, mutated, read back from text. Q64.

**F5. Axiom 3's qualifier gets stronger, not removed.** The M9 text said
name-level errors were "caught by the compiler rather than being
unrepresentable". Now they are unrepresentable *for generated
programs*. The qualifier that remains is about the compiler's role for
everything else, and about mutual recursion.

## Discussion

The pre-M16 machine was doing half its job and the experiments never
noticed, because every measurement of "well-formed" used `validates` —
which walked the same scope-blind machine. A generator that cannot see
names and a validator built from that generator agree perfectly with
each other and both miss 70% of the faults. Exp 02's 100% was true and
measured the wrong thing. F2's trap rate is the honest replacement: the
faults that remain are semantic, which is where Axiom 3 said they
would be.

Exp 10 has now moved three times — +20, +40, +32 — each time because
its samplers got the termination or scoping rule that the library
should have owned all along. Its next move should come from a
different experiment, not from fixing this one again.

## Next questions raised

- **Q64.** Mutual recursion is compilable but not generatable. A
  forward-declaration token would close it at one slot; a two-pass
  generator (bind the chain's names, then fill values) would close it
  at zero. Which, and is a generated mutually recursive pair worth
  either?
- **Q65.** 63% of generated programs now trap at run time. The trap
  kinds are known (`rt.caught` after a `try`-wrapped run would list
  them). Which are avoidable at generation — `div` with a literal
  zero, `head` of a literal `nil` — and would a *value*-aware machine
  be Axiom 3's next level, or overreach?
- **Q66.** Exp 02's headline (100% vs 0%) measured the generator with
  its own validator. It should be re-run with the compiler as the
  judge, which is what this experiment did; the number is 37% runnable
  against ~0% for unconstrained bytes, and that is the honest form.

## Status

Scope-aware generation takes unbound references in generated programs
from 70% to zero and runnable programs from 16% to 37%, closing Q54 and
making Axiom 3 hold at the name level for everything the generator
emits; the compiler remains the check for everything else, and mutual
recursion is the one shape it accepts that generation cannot reach.
