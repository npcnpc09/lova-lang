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
experiment is Q82; the harness is `experiments/experiment_17_llm_benchmark.py`
extended to a loop.

Single-shot pass@1 is the special case of one attempt and is already
at parity (Exp 17: 79/80 both). The numbers that can differ are the
other four.

## 4. What the measure asks of the design

Consequences, each a change the numbers above would reward:

- **The unit of editing is a path in the tree.** `lova_patch(path,
  replacement)` beside `lova_execute` in the MCP server: a fix costs
  the size of the fix, not the size of the file. The anomaly already
  names the path; the patch closes the loop.
- **A fault arrives with its fix, and the first fault stops the run.**
  Already the rule; keep it. A cascade of consequent errors is
  context spent for nothing.
- **Fewer names, and named fields instead of positions.** A record
  type with named access (Q84); pipeline composition in the library
  so that intermediate values need no name; a scope the runtime can
  list on request.
- **A program carries its examples.** A contract is a set of
  (inputs, expected) pairs the runtime can check at once, stored with
  the program and in its lineage.
- **The language ships its own card, generated.** The prelude's
  signatures and one line each, emitted by a command, so the card and
  the library cannot drift apart.
- **Intent lives in the lineage.** `why` is where the reason for a
  program goes; a source comment is for the person who happens to look.
- **Text is a value** (Q85) and a helper can carry an effect (Q86):
  the two taxes every text program and every effectful program paid.

## 5. On other languages

The paradigm-inheritance rule -- a feature without an ancestor
trajectory is suspicious -- served a language designed for people, and
is retired for design decisions. Other languages are a parts bin:
take what the numbers reward, owe nothing to precedent. The one thing
still borrowed on principle is the discipline of measuring.
