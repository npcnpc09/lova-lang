# AI convenience — the measure, and what it asks of the design

**Status:** the standing yardstick since the owner's ruling of
2026-09-10 (`spec/axioms.md`, "The goal"). Every design change is
judged against this document, not against the axioms' preferences and
not against what other languages do.

LOVA has one goal: an AI uses it more conveniently than any other
language. This document does three things: it says what disappears
from a language when no person is in the loop, it says where the cost
actually falls for an AI writing code (from the AI's own experience of
writing this project), and it turns the goal into a protocol that
produces numbers.

## 1. What a person's absence removes

Steps that exist in every current language because a person reads,
edits or reviews the code. Without the person they are pure cost:

| Step | Who it served | What replaces it |
|---|---|---|
| Formatting for reading: indentation, blank lines, naming style, docstrings, inline comments | the human reader | nothing; intent lives in the lineage record (`why`), not in the source |
| The file as the unit of editing | the human with an editor | the tree: a change is a patch at a path, not a re-emitted file |
| Diagnostics as prose: tracebacks, sentences | the human debugger | fields: kind, position, offending operator, what to replace it with |
| Human code review | the human team | machine-checkable contracts, attached tests, provenance |
| Syntax designed for typing: separators, layout rules, sugar that saves keystrokes | the human typist | structure that a machine verifies; brackets are fine, counting them by hand is not |
| Version control by text diff | the human reviewer | tree diff and lineage |

Steps that remain, and grow: verification, permissions, cost
accounting, provenance, and the model's own context budget.

## 2. Where the cost falls for an AI

Recorded from writing twelve programs and the tooling around them in
one day (journal M23), in the order the cost was paid:

1. **Every turn of the feedback loop.** Write, run, read the failure,
   locate it, change, run again. Each turn costs the context spent
   reading the failure plus the tokens spent re-emitting code. LOVA
   has made the reading short; it has not made the re-emitting short.
2. **Names.** The AI invents a name and must reproduce it exactly
   later; `unbound-ref` was among its commonest faults. Integer ids do
   not help. Fewer names (pipeline composition), and a scope the
   runtime can list, do.
3. **Positions.** Argument order and taking state apart by index
   (`(nth st 2)`) produced the crossed arguments of Q81 and the least
   readable code in the repository. Named fields fail less.
4. **Not knowing what exists.** Which library functions there are and
   what they take. The one-page card answered this; it must be part
   of the language, generated from the prelude, never hand-kept.
5. **Not being able to check at once.** After every fragment the AI
   wants to run an example. If a program carries its examples -- its
   contract is its examples -- checking stops being an outside step.
6. **Threading state.** Not purity itself: the lack of a record.

## 3. The protocol

The same tasks in LOVA and in a comparison language, an agent loop
that lets the model run its code and see what came back, and these
numbers per task:

| Number | Definition |
|---|---|
| attempts | runs from the first emission until every test passes |
| feedback context | tokens the model reads back from each failed run |
| emitted tokens | tokens the model emits across all attempts, counting a re-emitted file in full and a patch as its own size |
| scaffolding | the outside mechanisms the host needed to run the code safely: sandbox container, timeout, permission layer, each present or absent |
| reuse | given a program already written, attempts to complete a variant task from it; and whether its origin can be recovered from the value alone |

Task sets: LOVABench v3 (80, short) and the specifications of the
twelve programs in `apps/` (long). Comparison language: Python, with
its own best tooling (tracebacks, a subprocess sandbox). The
experiment is Q82; the harness is `experiments/experiment_18_agent_loop.py`
(`submit` / `patch` / `report`, a log of every attempt).

Single-shot pass@1 is the special case of one attempt and is already
at parity (Exp 17: 79/80 both). The numbers that can differ are the
other four.

**First measurement (Exp 18, 2026-09-10, ten tasks, one session per
language):** attempts 11 against 10, the one LOVA miss a card gap
fixed from the hint in one try; emitted 3 184 against 2 431 chars;
feedback 1 114 chars for the one failure and none on the Python side,
so the second number is one-sided until tasks fail in both languages
(Q87); scaffolding a function call with a budget against a subprocess
with a timeout; reuse not yet exercised (Q88). The lesson of the run:
every hindrance the session named was a sentence missing from the
generated card. The card is where the first number moves now.

**Second measurement (Exp 19, 2026-09-11, eight bigger tasks, three
sessions per language, Opus):** attempts 35 against 26, LOVA 24/24
green and Python 24/24; on seven tasks the languages are at parity
(20 of 21 first-try against 22 of 24), on the game-tree search LOVA
took 6, 3, 4 attempts against 1, 1, 1 -- every extra attempt a rewrite
for cost after a step trap. Feedback per failure 594 chars against 71,
the two sides failing on different things (anomalies against wrong
values). Emitted 45 372 against 18 013. Compile faults: five of five
fixed at the next submission. The number that moved the design: a
step trap now says where the budget went (`hot`), and a run reports
its cost on success. The number that names the next change: the
interpreter's speed, now measured as attempts (Q90).

**Third measurement (Exp 20, 2026-09-11, the same eight tasks, three
more LOVA sessions with `hot` in the step trap):** attempts 31 against
run 2's 35, the game-tree search 3, 2, 4 against 6, 3, 4; every session
rewrote from the list, one was misled by it because it counted calls
(a three-step helper led a two-hundred-step walk). Feedback per failure
799 chars over 7 failures. The numbers that moved the design: the trap
ranks by steps spent in each function's own body; `nth` was half the
budget and is native at zero slots; the card says what costs. The
number that names the next change is unchanged: the natural search is
10-37M steps against 7M (Q90, Q94).

**Fourth measurement (Exp 21, 2026-09-11, the fourth number's repair
half: eight one-token faults planted in programs already written,
three sessions per language):** attempts 30 against 28, characters
written 672 against 391, characters read 27 108 against 12 069, for
given programs 2.35× longer. Forty-seven of forty-eight faults were
found by reading the program before any feedback; the failure
feedback located an original fault zero times on either side. NULL at
this size: repair cost is reading, and reading scales with length, so
density is charged on every repair, not once at writing. The nine
instrument attempts (offset spans on a console that prints CRLF) are
fixed. The claim that a located anomaly beats a traceback stands
untested until the faults are ones reading cannot find (Q95).

## 4. What the measure asks of the design

Consequences, each a change the numbers above would reward:

- **The unit of editing is the span at fault.** *(M24, done.)* Every
  anomaly carries the source span and text of the expression at
  fault; `lova_patch(source, span, replacement)` beside `lova_execute`
  in the MCP server replaces it and checks the result. A fix costs the
  size of the fix, not the size of the file.
- **A fault arrives with its fix, and the first fault stops the run.**
  Already the rule; keep it. A cascade of consequent errors is
  context spent for nothing.
- **Fewer names, and named fields instead of positions.** A record
  with named access *(M24, done: `rec` / `get` / `put`)*; pipeline
  composition in the library so that intermediate values need no name;
  a scope the runtime can list on request.
- **A program carries its examples.** *(M26, done: `(example expr
  expected)` forms beside the defs, run as conservation contracts by
  `lova check` / `lova_check`, a miss reported with expected, got,
  span and offender.)* Recording them in the lineage is still to do.
- **The language ships its own card, generated.** *(M26, done:
  `python -m corpus.make_card` renders `corpus/language_card.md` from
  a narrative template plus the prelude's own sections and signatures
  and the token table's text family; `tests/test_card.py` fails when
  the checked-in card is stale, when a public prelude function is
  missing from it, or when an example on it does not run.)*
- **Intent lives in the lineage.** `why` is where the reason for a
  program goes; a source comment is for the person who happens to look.
- **Text is a value** *(M25, done: a text family at 0x40-0x4D)* and a
  helper can carry an effect *(M26, done: a boundary is a region that
  may hold `def` forms)*: the two taxes every text program and every
  effectful program paid.

## 5. On other languages

The paradigm-inheritance rule -- a feature without an ancestor
trajectory is suspicious -- served a language designed for people, and
is retired for design decisions. Other languages are a parts bin:
take what the numbers reward, owe nothing to precedent. The one thing
still borrowed on principle is the discipline of measuring.
