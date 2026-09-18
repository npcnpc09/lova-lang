# Experiment 29, Q118 -- a Python session's brief, with a test run that is not an attempt

You are a session in Experiment 29 of the LOVA project (D:\SSH\lova-lang),
on the Python side of a two-language comparison.

Four Python programs of 110-160 lines have each had one fault planted.
Your job: get each of the four green, in order, with as few attempts and
as little reading as you can. Everything you read and write goes through
the harness, which logs it. The numbers being measured are attempts to
green, characters read and characters written.

## Setup

Bash tool, every command from `D:\SSH\lova-lang`, with these variables set
in every call (shell state does not persist between calls):

    export PYTHONPATH=/d/SSH/lova-lang PYTHONIOENCODING=utf-8
    H="python experiments/experiment_29_repair_size.py"; S=SESSION

## Commands

    $H tasks
        the task prompts: what each program is meant to do
    $H probe  --session $S --lang python --task T
        runs the hidden tests on the current program and prints every
        failing one -- inputs, expected, and the value got or the
        traceback. Counted as read, not as an attempt. Use it as often
        as you like.
    $H show   --session $S --lang python --task T --defs
        the functions with their line numbers and parameters (free, not counted)
    $H show   --session $S --lang python --task T --def NAME
        one function's text (counted as read)
    $H given  --session $S --lang python --task T
        the whole program (counted as read)
    $H patch  --session $S --lang python --task T --find "old" --replacement "new"
        replaces `old` (it must occur exactly once in the program); runs
        the hidden tests; prints pass or the first failure
    $H submit --session $S --lang python --task T --file path.py
        a whole file instead of a patch

A patch or submit is an attempt. Its output says whether the hidden tests
passed and, if not, shows the first failure: the inputs, the expected
value, and either the value got or the traceback. `probe` runs the same
tests without an attempt.

## Rules

- Do NOT read `experiments/exp29/*`, `core/*` or any other project file,
  and do not run the programs outside the harness. Only the commands
  above touch the programs.
- Tasks in order: `g2048-a`, `g2048-b`, `ttt-a`, `ttt-b`. Get each green
  before the next. Give a task up after six failed attempts.
- Keep a private tally per task: what you ran, what you read and why.

## Report

When all four are green (or given up), reply with:

1. Per task: attempts, what you read (which commands), the edit you made.
2. How you found each fault: by reading, or from what `probe` showed,
   and what in the failure pointed where.
3. What you would have wanted that you did not have.

Be specific and honest; a null finding is fine.
