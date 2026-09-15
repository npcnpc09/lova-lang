# Experiment 25 — The policy layer of a real tool, in LOVA

**Date:** 2026-09-15
**Script:** none; the artefacts are `lib/fleet.lova`, `apps/fleet.lova`
and `tests/test_fleet.py`.
**Status:** Done. **PARTIAL (pilot).**

## Hypothesis

The four numbers of `spec/ai-convenience.md` are meant to be taken on
the same task in LOVA and in another language. Every task they have
been taken on so far was written for the purpose. This one was not:
RemoteX (`D:/SSH/RemoteX`) is an SSH fleet manager in daily use — a
PyQt5 desktop, a web terminal, and an MCP server of 38 tools that
Claude Code drives — and the question is whether LOVA can carry the
half of it that decides, and whether number (3), *what scaffolding a
host needs to run the code safely*, is visibly better where the code
runs commands on production servers.

## Method

Two pieces of RemoteX were ported from its JavaScript, and one piece
that does not exist in it was written:

- `resolveActiveToolNames` (`src/mcp-server.js`) — which of the 38
  tools a session advertises, from `REMOTEX_TOOLS` and
  `REMOTEX_TOOL_GROUPS`, with the banner's
  `Math.round((1 - active/total) * 100)`.
- `healthCheck`'s parse (`src/bridge.js`) —
  `stdout.split(/___(\w+)___/).filter(Boolean)` and the pairing loop.
- **The judgement**, which is not there: `healthCheck` returns five
  strings and stops, so what counts as unhealthy lives in the model's
  head, one machine at a time.

`tests/test_fleet.py` holds a transliteration of both ported pieces and
compares them: 140 activation cases, and thousands of generated strings
for the parse. The reference passes `re.ASCII`, because JavaScript's
`\w` is ASCII and Python's is Unicode — without that the test would
have been checking a different regular expression.

Nothing was run against a real server. The app reads a *recorded*
sweep.

## Results

**Agreement.** 18 tests. Activation agrees on all 140 combinations
including the rounding; the parse agrees on every generated string,
the hand-written pathological ones included.

**Cost.** 11 100 LOVA steps a machine; 2.2 M for two hundred, about
4.4 s on CPython and under a second on PyPy. The JavaScript does the
same work in milliseconds. Replacing a character-at-a-time walk with
`text-find` took the per-machine figure from 17 800 to 11 100.

**Defects the differential test found, and a look at the output would
not have:**

- F1. `sections` never emitted the text after the last marker, so
  `uptime` was missing from every reading.
- F2. `decimals` took the next *n characters* after the point instead
  of the next *n digits*, so `18.2 16.0` read as 18.02.
- F3. One reader was used for four shapes of reading. `12G/40G (31%)`
  has a perfectly good number at the front that means nothing. There
  are four readers now and each says which shape it is for.
- F4. An empty reading does not shift the fields after it, as assumed
  when the test was written — it **merges the two markers around the
  gap**, because `_` is a word character and the regex is greedy:
  `cpu` and `mem` both vanish and a field named `cpu______mem` appears.
  The original does this too.

**A number that is a decision, not a defect.** 3129/7823 is 39.997 per
cent. The shell prints `40.0` with `%.1f`; the exact integer ratio
truncated is 39.9. It is rounded, once, in one place, with the reason
beside it — which is what an integer language buys: the last digit is a
stated choice rather than whatever the float did.

## Findings

**F5. Number (3) is the one LOVA wins, and it is not close.** To run
this policy safely a host needs one flag: `--allow fs-read`.
`lib/fleet.lova` declares no boundary and contains no effect at all —
a test asserts it — so no edit to the policy can reach a socket, a
file or a command, and the compiler refuses before the run rather than
the reviewer refusing after it. In RemoteX the policy and the SSH
transport are the same module with the same permissions, and the
dangerous tools are gated by an environment variable.

**F6. Text is where every defect was.** Four of the four defects above
are in reading text. LOVA has no pattern matching, so reproducing one
JavaScript regular expression took forty lines of hand-written greedy
matching with backtracking. Every other part of the port — the tool
table, the set arithmetic, the thresholds, the sort — was written once
and was right the first time.

**F7. The paren checker is worth about four round trips per five
hundred lines.** Four times earlier the same day, a miscounted closing
paren on a nested curried lambda was reported as `lambda: expects 2
args, got 4` three hundred characters away from the fault. A
twenty-line balance checker, run before the compiler, cost zero round
trips on this file.

## Discussion

The honest limit of this experiment is that it is not a head-to-head.
The JavaScript already exists and works, so there is no attempt count
to compare against; what was measured is agreement, cost, and what the
host has to do. Four build-and-test rounds took `lib/fleet.lova` from
first write to green, with five defects in the LOVA and three wrong
expectations in the test — a single trajectory, and by the journal's
own convention a **pilot**.

F6 is the finding that bears on the language rather than on this port.
The ruling of 2026-09-11 says a feature enters only with evidence that
an AI needs it, and that an ancestor is not a reason. This is that kind
of evidence: a real task, a real cost, and a defect rate concentrated
in exactly the operation the language cannot express. A program that
reads what a shell printed is not a corner of the language's purpose —
it is most of what an agent does with a machine.

## Next questions raised

- **Q109: does the language need a pattern operator?** Not a regex
  engine — the question is what the smallest thing is that would have
  made F1 to F4 impossible. Candidates: a `split-on` that takes a
  delimiter and returns the pieces with their separators; a `scan` that
  takes a shape and returns the parts; a matcher over a small explicit
  grammar. It cannot be a macro over the core, so it costs a slot, and
  `spec/token-budget.md` says eight are free. Measure before spending:
  the same four readers, written both ways, counted in defects and in
  steps.
- **Q110: should the balance of a form be checked before the parser
  reports arity?** F7 says the fault an AI actually makes is not the
  fault the message names.
- **Q111: what is the cost of the policy at fleet scale under PyPy,**
  and does the 4.4 s figure matter at all when every reading behind it
  cost an SSH round trip with a ten-second timeout?

## Status

LOVA carries the deciding half of a real tool, agrees with the
JavaScript it was taken from everywhere it was compared, and needs one
flag from its host to be safe — but every defect on the way was in
reading text, which is the operation it cannot express (pilot).
