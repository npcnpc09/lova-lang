# Experiment 22 — The three-form experiment: which form does the model emit? (Q100)

**Date:** 2026-09-11
**Script:** `experiments/experiment_22_three_forms.py`
**Status:** In progress. Cost axis done; generation axis running. **PARTIAL so far.**

## Hypothesis

The ruling of 2026-09-11 (`CLAUDE.md`, "The design method"): the
model's behaviour decides between representations by measured
experiment, and a decision made on the s-expression is a decision made
with human-language intuition in the room. LOVA has three forms of the
same program:

- **s1** — the Stage-1 s-expression: parentheses, operator names.
- **s2** — the Stage-2 surface: one symbol per byte, no parentheses,
  integer references (`core.surface2`).
- **tok** — the raw token bytes, the substrate itself, written as
  space-separated decimal byte values (`core.tokens.encode`).

Axioms 1 and 2 assert the integer sequence is the program and the text
is a projection. Q47 has always asked whether a model can *emit* the
non-text forms at all. Q100 asks the design question on top of it:
across the AI's operations — emit, and (a later leg) repair — which
form does the model produce most reliably, at what token cost? If the
substrate forms cost more and are produced less reliably, "text is a
projection" is a true statement about the runtime and a false one about
convenience, and the case for Stage 2/3 rests only on density.

## Method

Ten **closed** programs (no inputs, one known integer answer each),
expressible in the core operators plus the list and text families and
nothing from the prelude — because the prelude is a Stage-1 text
construct: its names are integers in the substrate, and s2/tok have no
include mechanism, so operator-only is the only footing on which the
identical program exists in all three forms. `dry-run` confirms every
task round-trips and evaluates to its answer in all three.

Two measurements:

- **Cost axis (no model).** One canonical solution per task, rendered
  three ways, measured in LLM tokens (tiktoken cl100k_base), surface
  characters, and bytes. Form-intrinsic; nothing to do with what a
  model has seen.
- **Generation axis (Q47).** A fresh session is given one form's card
  — the three cards differ only in how a call is written, the operator
  set is identical — and writes the ten programs in that form.
  `submit` assembles the form back into a tree, compiles, runs, checks
  the answer. Pass@1 and the LLM-token cost of what was emitted are
  logged. Sessions run on Opus 4.8, the model the earlier legs used.

The confound is named, not hidden: a frontier model has read millions
of lines of Lisp-like text and zero of Stage-2 or raw LOVA bytes. The
cost axis is immune to it; the generation axis measures reliability
*given that exposure*, which is the situation any real use starts from.

## Results

### Cost axis (deterministic)

LLM tokens to write the ten programs:

| form | LLM tokens | surface chars | bytes |
|---|---|---|---|
| s1 (s-expression) | 192 | 448 | — |
| s2 (Stage-2 surface) | 141 | 146 | — |
| tok (decimal bytes) | 520 | — | 265 |

- **s2 is 1.36× cheaper than s1** in LLM tokens on this dense
  operator-only code — consistent with Exp 14's 1.13× on algorithmic
  tasks, and far below the 5.38× the number-theory built-ins gave,
  because here neither form has a built-in shortcut. The density win of
  the substrate projection is real but modest where the program is
  already dense.
- **tok is 2.71× more expensive than s1.** The substrate written as
  bytes for a model to emit is the costliest form, not the cheapest:
  cl100k tokenises `1 1 48` and two-digit byte values into many tokens,
  and the length-prefix arithmetic adds bytes. "The integer is the
  program" is a statement about identity and storage, not about what is
  cheap for a model to produce.
- One thing the build surfaced: the Stage-2 symbols for the list and
  text families are Greek capitals (Α, Β, …), non-ASCII single
  characters. They render as mojibake on a Windows console and can be
  mangled by any text pipeline that is not UTF-8 clean — a hazard the
  ASCII s-expression does not have, and a cost of the dense projection
  that the token count does not show.

### Generation axis

*(running — sessions on Opus 4.8, `report` fills this in)*

## Findings

- **F1 (cost).** On dense operator-only code the Stage-2 surface saves
  a third of the LLM tokens against the s-expression, and the raw-byte
  form costs nearly three times as much. The density argument for the
  substrate is Stage-2's alone, and it is modest here; the pure-token
  form is the most expensive thing to emit, which is the opposite of
  what "programs are integers, not text" suggests about convenience.
- *(generation findings pending)*

## Discussion

*(pending the generation axis; the shape of the argument: if s1 is
emitted far more reliably than s2 and s2 saves only a third of the
tokens, the text layer earns its place for a current model, and the
substrate forms are storage and identity, not the authoring surface —
which would make Axiom 2's "human readability is a non-goal of the
substrate" true and Axiom 1's "programs are integers, not text"
irrelevant to convenience until a model is trained on the bytes. If s2
is emitted about as reliably as s1, the text layer is removable now.)*

## Next questions raised

- *(pending)*

## Status

**PARTIAL, in progress.** The cost axis is measured: Stage-2 saves a
third of the LLM tokens on dense code, the raw-byte form costs 2.71×,
and the Stage-2 symbol set is non-ASCII. The generation axis is
running on Opus 4.8.
