# Experiment 17 — A model writes LOVA from one page

**Date:** 2026-09-10
**Script:** `experiments/experiment_17_llm_benchmark.py`
**Status:** In progress. First data point recorded (Claude, blind). **PARTIAL.**

## Hypothesis

M8's question: does a model write LOVA at least as reliably as it
writes Python, on the same tasks, single-shot? Exp 07 answered it with
the language's author transcribing formulas (60/60 vs 59/60) and Exp 13
F3 said that measured transcription. This experiment asks a model that
has never seen the codebase, gives it the one-page language card and
nothing else, and takes one answer per task with no execution and no
feedback.

## Method

`corpus/language_card.md` (the language on one page; its examples
were changed first so that none is a benchmark task) plus the 80
prompts of LOVABench v3, handed to a fresh Claude session (Fable 5.1)
with no tools and no repository access, with the instruction to answer
each task once as a single program and reply with JSON only. A second
fresh session got the same 80 prompts and wrote Python (`def solve`,
standard library only). Both replies were scored by the harness:
LOVA through the benchmark evaluator (prelude in scope, compiler on),
Python in a subprocess with a timeout. Zero tool uses in either
session; ~50 000 tokens each; 46 s and 110 s.

Categories: v1-core (pb01-20), deep-compose (21-30), conserve (31-40),
surprise (41-50), let-heavy (51-60), algorithmic (61-80; Q33).

## Results

| Category | n | LOVA | Python |
|---|---|---|---|
| v1-core | 20 | 19 | 19 |
| deep-compose | 10 | 10 | 10 |
| conserve | 10 | 10 | 10 |
| surprise | 10 | 10 | 10 |
| let-heavy | 10 | 10 | 10 |
| algorithmic | 20 | **20** | **20** |
| **all** | 80 | **79** | **79** |

The one failure is the same task in both languages, pb19, whose v1
prompt said "return the last value (p(5))" while its tests vary n;
both sessions did what the prompt said. The prompt now says p(n).

Answers: `experiments/results_17/claude_blind_answers.json`; scores:
`experiments/results_17/claude-blind.json`. The LOVA answers are
idiomatic without having seen the prelude's source: `(let ds (digits
{n}) (same ds (reverse ds)))` for the palindrome, a three-parameter
accumulator for Fibonacci, `(pow {b} {e})` where the card offered it,
`(seq (p 3) (p 4) (p 5))` for the sequence task.

## Findings

**F1. Given one page, a frontier model writes LOVA single-shot as
reliably as it writes Python on this benchmark: 79/80 against 79/80,
the same task missed for the same reason.** Neither the s-expression
surface nor the unfamiliar operator names cost a single task; the
algorithmic category, where prompts say what and not how, is 20/20 in
both.

**F2. The benchmark cannot separate the two languages at the top.**
Both are at the ceiling; the difference M8 was designed to measure,
if it exists, is not in pass@1 on tasks of this size. Where a
difference could appear: larger programs (the games, the sandbox --
hundreds of nodes, state threaded by hand), weaker models, and the
loop after a failure, where LOVA's structured anomaly replaces a
traceback. None of those is pass@1 on eighty one-liners.

**F3. The prompt defect the model exposed was the benchmark's, not the
model's.** pb19 had been misleading since v1; every author-written
solution used `{n}` because the author knew the tests. A blind reader
read the prompt.

**F4. The fine-tune's baseline is now known for this model: there is
nothing to gain on v3.** A fine-tune of a smaller model (M8's original
plan, ~$2.31 on gpt-4o-mini) still has a question to answer -- whether
a model that cannot write LOVA from a page can be taught to -- but for
the model most people write code with, the page is enough.

## Discussion

The owner's framing put this run within reach: most people write code
with Claude, so the model that matters is Claude, and Claude can be
asked without an API key by starting a session that knows nothing.
The result is the honest form of Exp 07: the same 79/80 shape, with
the author out of the loop and the prompts fixed where they leaked.

What the number does not say is that LOVA is *better*. It says that
for this model the language is free -- no reliability is lost by
writing it -- which moves the argument for LOVA entirely onto what the
program gets at run time: the structured fault, the budget, the
declared boundary, the lineage. Those are the claims the twelve
programs demonstrate, and they are not benchmark claims.

## Next questions raised

- **Q82.** Pass@1 on eighty short tasks saturates. What benchmark would
  separate the languages for a frontier model: programs of the size
  of `tictactoe.lova`, written blind from a specification? A repair
  loop -- the model fixes its own failure from the anomaly versus from
  a traceback -- scored on attempts to green?
- **Q83.** Exp 17 with a smaller model, and then its fine-tune, is
  three commands and a working key (`m8_finetune.py`). Is the
  question "can a small model be taught LOVA" still worth the run, now
  that the large one needs no teaching?

## Status

A fresh Claude given one page of LOVA and eighty tasks writes 79/80
correct, single-shot, the same as its Python; the one miss was a
misleading prompt, now fixed. The benchmark is at its ceiling for this
model, and the case for LOVA rests on what programs get at run time,
not on pass@1.
