# Experiment 21 — The repair leg: a fault planted in a program already written

**Date:** 2026-09-11
**Script:** `experiments/experiment_21_repair.py` (on Exp 18's harness; Exp 19's tasks)
**Status:** Done, three sessions per language, one model (Opus). **NULL** for the language, **WIN** for the measurement.

## Hypothesis

Q88, the yardstick's fourth number: the cost of repairing code already
written. Axiom 7 says surprise is the debugger; the claim to test is
that a structured anomaly with a span costs an agent less to act on
than a traceback or a wrong value. If it does, a session given a
faulty program should reach green in fewer attempts, or writing fewer
characters, in LOVA than in Python.

## Method

Exp 19's eight tasks. For each, a program written for it -- the LOVA
one by session o5 of Exp 20 as it passed, the Python one the harness's
reference -- with one semantic fault planted at the analogous place in
both languages: unary minus dropped (h01), the period not stripped
(h02), warnings sorted ascending (h03), the anti-diagonal replaced by
a duplicate of the diagonal (h04), a count where a sum was meant
(h05), `<` for `<=` on a touching interval (h06), an undirected edge
relaxed one way (h07), `<` for `<=` on a withdrawal (h08). Every
planted program compiles and runs; every fault fails at least one
hidden test (two tests were added so that this holds, one found by
searching the legal boards). `dry-run` checks both.

A session gets the task prompt, `given` (the program; its characters
logged as context read), and repairs it with `patch` (one character
span, counted as the replacement's size) or `submit` (a whole file);
`check` compiles for free. Three fresh Opus sessions per language,
r1-r3; the LOVA sessions have the card, the Python sessions nothing.

## Results

| lang | session | green | first-try | attempts | patches | emitted | read (given + feedback) | extra attempts, cause |
|---|---|---|---|---|---|---|---|---|
| LOVA | r1 | 8 | 4 | 12 | 12 | 227 | 10 154 | 3 bad spans, 1 misread of "touching" |
| LOVA | r2 | 8 | 7 | 9 | 9 | 288 | 8 489 | 1 bad span |
| LOVA | r3 | 8 | 7 | 9 | 9 | 157 | 8 465 | 1 bad span |
| Python | r1 | 8 | 8 | 8 | 8 | 85 | 3 459 | -- |
| Python | r2 | 8 | 6 | 10 | 10 | 184 | 4 585 | 2 bad spans |
| Python | r3 | 8 | 6 | 10 | 10 | 122 | 4 025 | 2 bad spans |
| LOVA | all | 24 | 18 | 30 | 30 | 672 | 27 108 | 5 spans, 1 misdiagnosis |
| Python | all | 24 | 20 | 28 | 28 | 391 | 12 069 | 4 spans |

The given programs: LOVA 8 141 characters for the eight, Python 3 459
(2.35×). Every repair on both sides was a patch; no session submitted
a whole file. Per fault, the fix was 2 to 85 characters in LOVA and 1
to 62 in Python, the large ones the same fault (h07, a second
relaxation / a second adjacency entry).

**Where the faults were found.** In 47 of 48 task-instances the
session found the fault by reading the program against the prompt and
its first submission passed, or failed only on its own patch. The
harness's failure feedback located an original fault zero times on
either side. The one semantic failure a session read (LOVA r1, h06:
`expected "1-5 6-8 12-20", got "1-8 12-20"`) corrected its reading of
"touching" in one attempt.

**Where the extra attempts went.** Nine of the ten were the
instrument: `patch` takes character offsets into a program the
session can only see printed, and on a Windows console the print
carries CRLF while the stored program has LF, so an offset computed
from a saved copy drifts by one per preceding line; the rest were hand
counts off by one or two. The anomalies those bad patches produced
located them exactly on both sides -- LOVA `parse-error` /
`unbound-ref` with span, line and column and "Nearest: w3"; Python
`SyntaxError` with line and caret -- and each was undone at the next
submission.

**What the sessions said**, in substance, all six: "at this program
size the language's error model is not on the critical path; the cost
is read the spec, read the program, spot the divergence"; "feedback
located zero of the eight original faults; it located 3/3 of my own
injected faults, precisely"; every session asked for a patch addressed
by text rather than offset, and a dry run.

## Findings

- **F1. At this size, repair is reading, and the languages do not
  separate on diagnostics.** 47 of 48 faults were found from the
  source before any feedback; Axiom 7's channel was never on the path.
- **F2. Repair cost scales with program length, and LOVA programs are
  longer.** Emitted 672 against 391 (1.7×), read 27 108 against 12 069
  (2.2×), for given programs 2.35× longer in characters. The fourth
  number is, at this size, the density number by another name.
- **F3. Attempts: 30 against 28, with 9 of the 10 extra attempts the
  instrument's.** With those removed, 21 against 24 -- LOVA's one
  real extra attempt was a reading of "touching" the prompt left open.
- **F4. When feedback was read, it worked, on both sides.** Five bad
  LOVA patches and four bad Python patches were each undone in one
  attempt from a located anomaly. The structured anomaly's advantage
  over a `SyntaxError` with a caret is not visible at one-line faults.
- **F5. The instrument's defect is the addressing scheme.** Character
  offsets into printed text, with CRLF on the console and no way to
  see what a span selects before paying. `patch --find <text>` (must
  occur once) and `--dry-run` are in the harness now; `given` no
  longer counts as an attempt in the numbering.
- **F6. The claim needs faults that reading cannot find.** A one-token
  spec mismatch in twenty lines is found by inspection in any language.
  Where an anomaly with a span could pay is a run-time fault deep in a
  program too long to reread -- the app-sized programs of M23 -- or a
  fault whose symptom is far from its cause. None of the eight was
  that.

## Discussion

The honest reading is NULL for the language: on the repair leg as
measured here, LOVA is at parity in attempts and behind in characters,
by the ratio of its program lengths, and its error model never got to
speak. The sessions' own words are the finding: the cost was reading,
and reading a longer program costs more.

That is also what the measurement was for. The fourth number was
unmeasured, and the design had a claim riding on it -- surprise-guided
repair, spans, `lova_patch` -- that this run does not support at this
size. It does not refute it either: every anomaly that was read
located its fault in one attempt, which is what Exp 18-20 found for
compile faults. What it shows is that the claim lives at a size and a
fault class this experiment did not reach.

Two things move the design. First, density is now a repair cost too:
a 2.35× longer program is 2.2× more to read every time it is touched,
so the Stage-1 surface's verbosity is charged on every repair, not
once at writing. Second, `(example ...)` forms were on none of the
given programs, and a session pointed out that h03's ordering and
h08's boundary would have been visible in an example without running
anything -- a program that carries its examples is cheaper to repair,
and the corpus does not yet carry them.

## Next questions raised

- **Q95** -- the repair leg at a size where reading fails: faults
  planted in `apps/`-sized programs (100+ lines), with run-time
  symptoms (a trap, a wrong value far from its cause) rather than
  spec mismatches; the span and `hot` against a traceback, on the
  same faults.
- **Q96** -- does a program that carries `example` forms get repaired
  in fewer attempts than the same program without them? The given
  programs of this experiment with examples added, three sessions.
- **Q97** -- density as a repair cost: the read count is 2.2× per
  touch; what does the Stage-2 surface (1.13× Python) do to it?

## Status

**NULL for the language, WIN for the measurement.** The fourth number
has its first value: 30 attempts against 28, 672 characters written
against 391, 27 108 read against 12 069, on eight one-token faults
that every session found by reading before any feedback. Nine of the
ten extra attempts were the harness's offset addressing, fixed
(`--find`, `--dry-run`). Q95-Q97 raised.
