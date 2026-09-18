# Experiment 29, Q120 -- a LOVA session's brief; the tasks are named in your instruction

You are a session in Experiment 29 of the LOVA project (D:\SSH\lova-lang).
LOVA is a small programming language; its one-page card is at
`corpus/language_card.md`. Read it first (that read is not counted).

Four programs of 110-160 lines have each had one fault planted. Your job:
get each of the four green, in order, with as few attempts and as little
reading as you can. Everything you read and write goes through the
harness, which logs it. The numbers being measured are attempts to green,
characters read and characters written.

## Setup

Bash tool, every command from `D:\SSH\lova-lang`, with these variables set
in every call (shell state does not persist between calls):

    export PYTHONPATH=/d/SSH/lova-lang PYTHONIOENCODING=utf-8
    H="python experiments/experiment_29_repair_size.py"; S=SESSION

## Commands

    $H tasks
        the task prompts: what each program is meant to do
    $H fault  --session $S --lang lova --task T
        runs the program's own examples; prints each failing one with
        expected/got or the trap it hit, and a `fault:` line where a single
        edit of one def makes the examples pass, with the replacement text
        and how many examples it fixes. Slow on the noughts-and-crosses
        tasks (up to ~2 minutes): give the Bash tool a timeout of 300000.
    $H show   --session $S --lang lova --task T --defs
        the defs with their spans and sizes (free, not counted)
    $H show   --session $S --lang lova --task T --def NAME
        one def's text (counted as read)
    $H given  --session $S --lang lova --task T
        the whole program (counted as read)
    $H patch  --session $S --lang lova --task T --def NAME --find "old" --replacement "new"
        replaces `old` inside def NAME (it must occur once in that def);
        runs the hidden tests; prints pass or the first failure
    $H patch  --session $S --lang lova --task T --span START END --replacement "new"
        the same by the span the `fault:` line prints, `[START, END)`
    $H submit --session $S --lang lova --task T --file path.lova
        a whole file instead of a patch

A patch or submit is an attempt. Its output says whether the hidden tests
passed and, if not, shows the first failure (expected/got, or the anomaly
with its span and excerpt).

## Rules

- Do NOT read `experiments/exp29/*`, `core/*`, `lib/*` or any other project
  file, and do not run the programs outside the harness. Only the commands
  above touch the programs.
- Your tasks, in order, are named in the instruction that sent you here
  (two of them). Get each green before the next. Give a task up after
  six failed attempts.
- Keep a private tally per task: what you ran, what you read and why,
  and whether you applied the `fault:` line's replacement without
  reading the def ("blind") or read first.

## Report

When all four are green (or given up), reply with:

1. Per task: attempts, what you read (which commands), blind or read, the
   edit you made.
2. What the `fault:` line did for you, in your own words: when you
   trusted it, when not, and why.
3. What you would have wanted that you did not have.

Be specific and honest; a null finding is fine.
