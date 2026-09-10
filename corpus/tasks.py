"""LOVABench v2 — 60 parametrised number-theory composition tasks —
and v3, which adds twenty algorithmic ones (pb61-pb80, ``ALGORITHMIC``,
``TASKS_V3``; Q33).

Each task is a triple of (natural-language prompt, LOVA template,
list of test cases). The template uses ``{var}`` placeholders for
inputs; the evaluator substitutes test inputs and runs the resulting
program through the LOVA runtime.

Structure (v2 = v1 + four 10-task extensions):

  pb01-pb20: **v1 core** — single primitives + shallow compositions
             + let/seq/surprise basics (the Exp 07 / Exp 11 set).
  pb21-pb30: **deep composition** — 3-4 level nesting. Stresses
             Python's with-each-step-longer verbosity while LOVA
             stays compact.
  pb31-pb40: **conserve-heavy** — programs wrapped in ``(conserve E
             body)``. Python has no native conservation contract;
             translation either asserts (shorter) or ignores the
             invariant (cheats). Measures a LOVA-unique feature.
  pb41-pb50: **surprise-based** — ``surprise`` (deviation value) and
             ``if-surprise`` (branch on deviation). Same story as
             conserve: Python-native lacks the primitive.
  pb51-pb60: **let-heavy** — shared subexpressions via ``let`` /
             ``ref``. Exercises binding scope for tokeniser density
             under "avoid repeating computation" patterns.

Why not HumanEval?  HumanEval is dominated by string / list
manipulation that LOVA M1-M2 cannot express (no strings, no lists,
no loops, no subtraction, no multiplication).  LOVABench picks
tasks that are natively expressible in LOVA's **present** expressive
power (19 M1-M6 operators, Int/LiteralInt types) so that we measure
the substrate fairly.  Future benchmarks will expand as effect /
evolution / meta families come online (M7+).

Every task's reference solution is **hand-written and known to
validate**.  The evaluator confirms this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


TestCase = Tuple[Dict[str, int], int]  # (input bindings, expected output)


@dataclass(frozen=True)
class Task:
    """A single LOVABench task."""
    id: str
    name: str
    prompt: str           # natural-language description (for LLM prompting)
    template: str         # LOVA s-expression with ``{var}`` placeholders
    tests: Tuple[TestCase, ...]
    tags: Tuple[str, ...] = field(default_factory=tuple)


# LOVABench v2 — 60 canonical tasks (v1 core + 4 × 10 extensions).
TASKS: Tuple[Task, ...] = (
    # --- single-primitive lookup (1-5) ------------------------------------
    Task(
        id="pb01",
        name="partition_number",
        prompt="Given an integer n, return the n-th partition number p(n).",
        template="(p {n})",
        tests=(({"n": 12}, 77), ({"n": 5}, 7), ({"n": 10}, 42)),
        tags=("nt", "recall", "single-op"),
    ),
    Task(
        id="pb02",
        name="divisor_count",
        prompt="Given an integer n, return the number of its divisors tau(n).",
        template="(tau {n})",
        tests=(({"n": 12}, 6), ({"n": 100}, 9), ({"n": 17}, 2)),
        tags=("nt", "recall", "single-op"),
    ),
    Task(
        id="pb03",
        name="divisor_sum",
        prompt="Given an integer n, return the sum of its divisors sigma(n).",
        template="(sigma {n})",
        tests=(({"n": 12}, 28), ({"n": 6}, 12), ({"n": 10}, 18)),
        tags=("nt", "recall", "single-op"),
    ),
    Task(
        id="pb04",
        name="gcd_two",
        prompt="Given two integers a and b, return gcd(a, b).",
        template="(gcd {a} {b})",
        tests=(({"a": 12, "b": 18}, 6),
               ({"a": 100, "b": 75}, 25),
               ({"a": 7, "b": 13}, 1)),
        tags=("nt", "recall", "binary"),
    ),
    Task(
        id="pb05",
        name="mobius",
        prompt="Given an integer n, return the Moebius function value mu(n).",
        template="(mobius {n})",
        tests=(({"n": 30}, -1), ({"n": 12}, 0), ({"n": 1}, 1)),
        tags=("nt", "recall", "single-op"),
    ),
    # --- simple composition (6-10) ----------------------------------------
    Task(
        id="pb06",
        name="p_of_tau",
        prompt="Compute the partition number of the divisor count of n: p(tau(n)).",
        template="(p (tau {n}))",
        tests=(({"n": 12}, 11),   # tau(12)=6, p(6)=11
               ({"n": 100}, 30),  # tau(100)=9, p(9)=30
               ({"n": 17}, 2)),   # tau(17)=2, p(2)=2  -- wait, p(2)=2
        tags=("nt", "composition", "depth-2"),
    ),
    Task(
        id="pb07",
        name="tau_of_p",
        prompt="Compute the divisor count of the partition number of n: tau(p(n)).",
        template="(tau (p {n}))",
        tests=(({"n": 12}, 4),   # p(12)=77, tau(77)=4
               ({"n": 5}, 2),    # p(5)=7,  tau(7)=2
               ({"n": 10}, 8)),  # p(10)=42, tau(42)=8 (42=2*3*7, tau=8)
        tags=("nt", "composition", "depth-2"),
    ),
    Task(
        id="pb08",
        name="sigma_of_tau",
        prompt="Compute the divisor sum of the divisor count of n: sigma(tau(n)).",
        template="(sigma (tau {n}))",
        tests=(({"n": 12}, 12),   # tau(12)=6, sigma(6)=12
               ({"n": 100}, 13),  # tau(100)=9, sigma(9)=13
               ({"n": 17}, 3)),   # tau(17)=2, sigma(2)=3
        tags=("nt", "composition", "depth-2"),
    ),
    Task(
        id="pb09",
        name="sum_p_tau",
        prompt="Compute p(n) + tau(n).",
        template="(merge (p {n}) (tau {n}))",
        tests=(({"n": 12}, 83),   # 77 + 6
               ({"n": 5}, 9),     # 7 + 2
               ({"n": 6}, 15)),   # 11 + 4
        tags=("nt", "composition", "merge"),
    ),
    Task(
        id="pb10",
        name="gcd_of_sigmas",
        prompt="Given two integers a and b, return gcd(sigma(a), sigma(b)).",
        template="(gcd (sigma {a}) (sigma {b}))",
        tests=(({"a": 12, "b": 18}, 1),    # gcd(28, 39)=1
               ({"a": 6, "b": 10}, 6),     # gcd(12, 18)=6
               ({"a": 4, "b": 9}, 1)),     # gcd(7, 13)=1
        tags=("nt", "composition", "binary"),
    ),
    # --- deeper composition (11-15) ---------------------------------------
    Task(
        id="pb11",
        name="p_p",
        prompt="Compute p(p(n)), the partition-of-partition.",
        template="(p (p {n}))",
        tests=(({"n": 5}, 15),   # p(5)=7, p(7)=15
               ({"n": 3}, 3),    # p(3)=3, p(3)=3
               ({"n": 4}, 7)),   # p(4)=5, p(5)=7
        tags=("nt", "composition", "depth-2"),
    ),
    Task(
        id="pb12",
        name="tau_of_gcd",
        prompt="Compute tau(gcd(a, b)).",
        template="(tau (gcd {a} {b}))",
        tests=(({"a": 12, "b": 18}, 4),    # gcd=6, tau(6)=4
               ({"a": 100, "b": 75}, 3),   # gcd=25, tau(25)=3
               ({"a": 7, "b": 13}, 1)),    # gcd=1, tau(1)=1
        tags=("nt", "composition", "binary-depth-2"),
    ),
    Task(
        id="pb13",
        name="sigma_gcd_plus_tau",
        prompt="Compute sigma(gcd(a, b)) + tau(a).",
        template="(merge (sigma (gcd {a} {b})) (tau {a}))",
        tests=(({"a": 12, "b": 18}, 18),   # sigma(6)=12, tau(12)=6, 12+6=18
               ({"a": 6, "b": 10}, 7),     # sigma(2)=3, tau(6)=4, 3+4=7
               ({"a": 4, "b": 9}, 4)),     # sigma(1)=1, tau(4)=3, 1+3=4
        tags=("nt", "composition", "depth-3"),
    ),
    Task(
        id="pb14",
        name="mobius_of_p",
        prompt="Compute mu(p(n)), the Moebius of the partition number.",
        template="(mobius (p {n}))",
        tests=(({"n": 3}, -1),   # p(3)=3, mu(3)=-1
               ({"n": 5}, -1),   # p(5)=7, mu(7)=-1
               ({"n": 6}, -1)),  # p(6)=11, mu(11)=-1
        tags=("nt", "composition", "depth-2"),
    ),
    Task(
        id="pb15",
        name="sigma_plus_mobius",
        prompt="Compute sigma(n) + mu(n).",
        template="(merge (sigma {n}) (mobius {n}))",
        tests=(({"n": 12}, 28),    # sigma(12)=28, mu(12)=0
               ({"n": 30}, 71),    # sigma(30)=72, mu(30)=-1, 72-1=71
               ({"n": 1}, 2)),     # sigma(1)=1, mu(1)=1, 1+1=2
        tags=("nt", "composition", "merge"),
    ),
    # --- let/ref / sequential / surprise (16-20) --------------------------
    Task(
        id="pb16",
        name="let_bound_tau_plus_sigma",
        prompt=("Let x = n; return tau(x) + sigma(x).  Must use a "
                "let-binding to hold x."),
        template="(let 0 {n} (merge (tau (ref 0)) (sigma (ref 0))))",
        tests=(({"n": 10}, 22),    # tau(10)=4, sigma(10)=18, 4+18=22
               ({"n": 6}, 16),     # tau(6)=4, sigma(6)=12, 4+12=16
               ({"n": 12}, 34)),   # tau(12)=6, sigma(12)=28, 6+28=34
        tags=("binding", "let-ref", "composition"),
    ),
    Task(
        id="pb17",
        name="p_of_gcd",
        prompt="Compute p(gcd(a, b)).",
        template="(p (gcd {a} {b}))",
        tests=(({"a": 12, "b": 18}, 11),    # gcd=6, p(6)=11
               ({"a": 100, "b": 75}, 1958), # gcd=25, p(25)=1958
               ({"a": 6, "b": 10}, 2)),     # gcd=2, p(2)=2
        tags=("nt", "composition", "binary-depth-2"),
    ),
    Task(
        id="pb18",
        name="triple_gcd",
        prompt="Compute gcd(gcd(a, b), c), the three-way gcd.",
        template="(gcd (gcd {a} {b}) {c})",
        tests=(({"a": 12, "b": 18, "c": 24}, 6),
               ({"a": 100, "b": 75, "c": 50}, 25),
               ({"a": 7, "b": 13, "c": 21}, 1)),
        tags=("nt", "recall", "ternary"),
    ),
    Task(
        id="pb19",
        name="seq_last_is_p",
        prompt=("Evaluate p(3), then p(4), then p(n) in sequence; return "
                "the last value, p(n)."),
        template="(seq (p 3) (p 4) (p {n}))",
        tests=(({"n": 5}, 7),      # p(5)=7
               ({"n": 10}, 42),    # p(10)=42
               ({"n": 12}, 77)),   # p(12)=77
        tags=("composition", "seq", "variadic"),
    ),
    Task(
        id="pb20",
        name="surprise_deviation",
        prompt=("Return the surprise (deviation) between a prediction `p` "
                "and the actual value of p(n)."),
        template="(surprise {p} (p {n}))",
        tests=(({"p": 77, "n": 12}, 0),    # perfect prediction
               ({"p": 10, "n": 12}, 67),   # p(12)=77, deviation=67
               ({"p": 5, "n": 5}, 2)),     # p(5)=7, deviation=2
        tags=("surprise", "binary"),
    ),
    # --- deep composition (21-30): 3-4 level nesting ----------------------
    Task(
        id="pb21",
        name="p_tau_sigma",
        prompt="Compute p(tau(sigma(n))) — three-level number-theory composition.",
        template="(p (tau (sigma {n})))",
        tests=(({"n": 12}, 11), ({"n": 6}, 11), ({"n": 4}, 2)),
        tags=("nt", "composition", "depth-3"),
    ),
    Task(
        id="pb22",
        name="sigma_gcd_pa_pb",
        prompt="Compute sigma(gcd(p(a), p(b))) for two integers a and b.",
        template="(sigma (gcd (p {a}) (p {b})))",
        tests=(({"a": 6, "b": 10}, 1),
               ({"a": 4, "b": 9}, 6),
               ({"a": 3, "b": 5}, 1)),
        tags=("nt", "composition", "depth-3", "binary"),
    ),
    Task(
        id="pb23",
        name="triple_tau",
        prompt="Compute tau(tau(tau(n))), three nested divisor-counts.",
        template="(tau (tau (tau {n})))",
        tests=(({"n": 24}, 3), ({"n": 30}, 3), ({"n": 12}, 3)),
        tags=("nt", "composition", "depth-3"),
    ),
    Task(
        id="pb24",
        name="mobius_gcd_sigma_tau",
        prompt="Compute mu(gcd(sigma(a), tau(b))).",
        template="(mobius (gcd (sigma {a}) (tau {b})))",
        tests=(({"a": 6, "b": 12}, 1),
               ({"a": 4, "b": 9}, 1),
               ({"a": 10, "b": 15}, -1)),
        tags=("nt", "composition", "depth-3", "binary"),
    ),
    Task(
        id="pb25",
        name="p_p_tau",
        prompt="Compute p(p(tau(n))).",
        template="(p (p (tau {n})))",
        tests=(({"n": 8}, 7), ({"n": 12}, 56), ({"n": 6}, 7)),
        tags=("nt", "composition", "depth-3"),
    ),
    Task(
        id="pb26",
        name="merge_ptau_sigmagcd",
        prompt="Compute p(tau(a)) + sigma(gcd(a, b)) — a four-level merge.",
        template="(merge (p (tau {a})) (sigma (gcd {a} {b})))",
        tests=(({"a": 6, "b": 12}, 17),
               ({"a": 10, "b": 15}, 11),
               ({"a": 4, "b": 9}, 4)),
        tags=("nt", "composition", "depth-4", "binary"),
    ),
    Task(
        id="pb27",
        name="gcd_sigma_tau_of_p",
        prompt="Compute gcd(sigma(p(n)), tau(p(n))).",
        template="(gcd (sigma (p {n})) (tau (p {n})))",
        tests=(({"n": 5}, 2), ({"n": 3}, 2), ({"n": 4}, 2)),
        tags=("nt", "composition", "depth-3"),
    ),
    Task(
        id="pb28",
        name="tau_merge_sigmas",
        prompt="Compute tau(sigma(a) + sigma(b)) — divisor-count of the sum of divisor-sums.",
        template="(tau (merge (sigma {a}) (sigma {b})))",
        tests=(({"a": 3, "b": 4}, 2),
               ({"a": 6, "b": 8}, 4),
               ({"a": 5, "b": 7}, 4)),
        tags=("nt", "composition", "depth-3", "binary"),
    ),
    Task(
        id="pb29",
        name="sigma_p_gcd",
        prompt="Compute sigma(p(gcd(a, b))).",
        template="(sigma (p (gcd {a} {b})))",
        tests=(({"a": 12, "b": 18}, 12),
               ({"a": 6, "b": 10}, 3),
               ({"a": 4, "b": 9}, 1)),
        tags=("nt", "composition", "depth-3", "binary"),
    ),
    Task(
        id="pb30",
        name="sigma_tau_plus_p_mu",
        prompt="Compute sigma(tau(n)) + p(mu(n)).",
        template="(merge (sigma (tau {n})) (p (mobius {n})))",
        tests=(({"n": 6}, 8), ({"n": 10}, 8), ({"n": 5}, 3)),
        tags=("nt", "composition", "depth-3"),
    ),
    # --- conserve-heavy (31-40): contract-verified computations -----------
    Task(
        id="pb31",
        name="conserve_p",
        prompt=("Compute p(n), verified to equal the expected value k via a "
                "conserve contract. Returns p(n); traps if p(n) != k."),
        template="(conserve {k} (p {n}))",
        tests=(({"n": 5, "k": 7}, 7),
               ({"n": 3, "k": 3}, 3),
               ({"n": 10, "k": 42}, 42)),
        tags=("conserve", "contract"),
    ),
    Task(
        id="pb32",
        name="conserve_tau",
        prompt="Compute tau(n), verified to equal k.",
        template="(conserve {k} (tau {n}))",
        tests=(({"n": 12, "k": 6}, 6),
               ({"n": 100, "k": 9}, 9),
               ({"n": 17, "k": 2}, 2)),
        tags=("conserve", "contract"),
    ),
    Task(
        id="pb33",
        name="conserve_gcd",
        prompt="Compute gcd(a, b), verified to equal k.",
        template="(conserve {k} (gcd {a} {b}))",
        tests=(({"a": 12, "b": 18, "k": 6}, 6),
               ({"a": 100, "b": 75, "k": 25}, 25),
               ({"a": 7, "b": 13, "k": 1}, 1)),
        tags=("conserve", "contract", "binary"),
    ),
    Task(
        id="pb34",
        name="conserve_p_plus_tau",
        prompt="Compute p(n) + tau(n), verified to equal k.",
        template="(conserve {k} (merge (p {n}) (tau {n})))",
        tests=(({"n": 5, "k": 9}, 9),
               ({"n": 10, "k": 46}, 46),
               ({"n": 12, "k": 83}, 83)),
        tags=("conserve", "contract", "composition"),
    ),
    Task(
        id="pb35",
        name="conserve_sigma_gcd",
        prompt="Compute sigma(gcd(a, b)), verified to equal k.",
        template="(conserve {k} (sigma (gcd {a} {b})))",
        tests=(({"a": 12, "b": 18, "k": 12}, 12),
               ({"a": 6, "b": 10, "k": 3}, 3),
               ({"a": 4, "b": 9, "k": 1}, 1)),
        tags=("conserve", "contract", "binary", "composition"),
    ),
    Task(
        id="pb36",
        name="conserve_mobius",
        prompt="Compute mu(n), verified to equal k (allows negative).",
        template="(conserve {k} (mobius {n}))",
        tests=(({"n": 30, "k": -1}, -1),
               ({"n": 12, "k": 0}, 0),
               ({"n": 1, "k": 1}, 1)),
        tags=("conserve", "contract", "negative"),
    ),
    Task(
        id="pb37",
        name="conserve_p_of_tau",
        prompt="Compute p(tau(n)), verified to equal k.",
        template="(conserve {k} (p (tau {n})))",
        tests=(({"n": 12, "k": 11}, 11),
               ({"n": 100, "k": 30}, 30),
               ({"n": 17, "k": 2}, 2)),
        tags=("conserve", "contract", "composition"),
    ),
    Task(
        id="pb38",
        name="conserve_let_tau_sigma",
        prompt=("Compute tau(n) + sigma(n) via a let-binding of n, "
                "verified to equal k."),
        template=("(conserve {k} (let 0 {n} (merge (tau (ref 0)) "
                  "(sigma (ref 0)))))"),
        tests=(({"n": 10, "k": 22}, 22),
               ({"n": 6, "k": 16}, 16),
               ({"n": 12, "k": 34}, 34)),
        tags=("conserve", "contract", "let-ref"),
    ),
    Task(
        id="pb39",
        name="let_outside_conserve_gcd",
        prompt=("Bind a to slot 0, then compute gcd(a, b) verified to "
                "equal k inside a conserve scope."),
        template="(let 0 {a} (conserve {k} (gcd (ref 0) {b})))",
        tests=(({"a": 12, "b": 18, "k": 6}, 6),
               ({"a": 100, "b": 75, "k": 25}, 25),
               ({"a": 7, "b": 13, "k": 1}, 1)),
        tags=("conserve", "let-ref", "binary"),
    ),
    Task(
        id="pb40",
        name="merge_two_conserves",
        prompt=("Compute (conserved p(n)) + (conserved tau(n)), given "
                "expected values k1 and k2 for each."),
        template=("(merge (conserve {k1} (p {n})) "
                  "(conserve {k2} (tau {n})))"),
        tests=(({"n": 5, "k1": 7, "k2": 2}, 9),
               ({"n": 10, "k1": 42, "k2": 4}, 46),
               ({"n": 12, "k1": 77, "k2": 6}, 83)),
        tags=("conserve", "contract", "merge"),
    ),
    # --- surprise-based (41-50): deviation + branching --------------------
    Task(
        id="pb41",
        name="surprise_k_p",
        prompt="Return |k - p(n)|, the surprise magnitude.",
        template="(surprise {k} (p {n}))",
        tests=(({"n": 5, "k": 10}, 3),
               ({"n": 12, "k": 77}, 0),
               ({"n": 3, "k": 3}, 0)),
        tags=("surprise", "deviation"),
    ),
    Task(
        id="pb42",
        name="surprise_k_tau",
        prompt="Return |k - tau(n)|.",
        template="(surprise {k} (tau {n}))",
        tests=(({"n": 12, "k": 10}, 4),
               ({"n": 100, "k": 9}, 0),
               ({"n": 17, "k": 2}, 0)),
        tags=("surprise", "deviation"),
    ),
    Task(
        id="pb43",
        name="surprise_p_p",
        prompt="Return |p(n) - p(m)|, the surprise between two partition numbers.",
        template="(surprise (p {n}) (p {m}))",
        tests=(({"n": 5, "m": 3}, 4),
               ({"n": 12, "m": 5}, 70),
               ({"n": 10, "m": 3}, 39)),
        tags=("surprise", "deviation", "composition"),
    ),
    Task(
        id="pb44",
        name="surprise_perfect_test",
        prompt=("Return |sigma(n) - 2n|, zero if n is a perfect number "
                "(6, 28, 496, ...)."),
        template="(surprise (sigma {n}) (merge {n} {n}))",
        tests=(({"n": 6}, 0),
               ({"n": 12}, 4),
               ({"n": 28}, 0)),
        tags=("surprise", "deviation", "perfect-number"),
    ),
    Task(
        id="pb45",
        name="is_p_of_n_equal_k",
        prompt=("Predicate: return 1 if p(n) equals k else 0 (zero-surprise "
                "picks branch 1)."),
        template="(if-surprise (surprise {k} (p {n})) 0 1)",
        tests=(({"n": 5, "k": 7}, 1),
               ({"n": 5, "k": 10}, 0),
               ({"n": 12, "k": 77}, 1)),
        tags=("surprise", "if-surprise", "predicate"),
    ),
    Task(
        id="pb46",
        name="are_coprime",
        prompt="Predicate: return 1 if a and b are coprime (gcd=1) else 0.",
        template="(if-surprise (surprise 1 (gcd {a} {b})) 0 1)",
        tests=(({"a": 7, "b": 13}, 1),
               ({"a": 12, "b": 18}, 0),
               ({"a": 6, "b": 10}, 0)),
        tags=("surprise", "if-surprise", "predicate", "binary"),
    ),
    Task(
        id="pb47",
        name="is_sigma_of_n_equal_k",
        prompt="Predicate: return 1 if sigma(n) equals k else 0.",
        template="(if-surprise (surprise {k} (sigma {n})) 0 1)",
        tests=(({"n": 12, "k": 28}, 1),
               ({"n": 6, "k": 12}, 1),
               ({"n": 10, "k": 20}, 0)),
        tags=("surprise", "if-surprise", "predicate"),
    ),
    Task(
        id="pb48",
        name="surprise_tau_sigma_swap",
        prompt=("Return |tau(sigma(n)) - sigma(tau(n))| — measures how far "
                "tau and sigma commute at n."),
        template="(surprise (tau (sigma {n})) (sigma (tau {n})))",
        tests=(({"n": 6}, 1), ({"n": 12}, 6), ({"n": 10}, 1)),
        tags=("surprise", "deviation", "depth-3"),
    ),
    Task(
        id="pb49",
        name="is_squarefree",
        prompt=("Predicate: return 1 if n is squarefree (mu != 0), else 0. "
                "Non-zero surprise from 0 picks branch 1."),
        template="(if-surprise (surprise 0 (mobius {n})) 1 0)",
        tests=(({"n": 30}, 1), ({"n": 12}, 0), ({"n": 1}, 1)),
        tags=("surprise", "if-surprise", "predicate"),
    ),
    Task(
        id="pb50",
        name="surprise_p_diff_via_let",
        prompt=("Return |p(a) - p(b)|, binding a and b via nested lets "
                "before computing."),
        template=("(let 0 {a} (let 1 {b} (surprise (p (ref 0)) "
                  "(p (ref 1)))))"),
        tests=(({"a": 5, "b": 3}, 4),
               ({"a": 7, "b": 5}, 8),
               ({"a": 10, "b": 12}, 35)),
        tags=("surprise", "let-ref", "deviation"),
    ),
    # --- let-heavy (51-60): shared subexpressions via binding -------------
    Task(
        id="pb51",
        name="let_p_plus_tau",
        prompt="Let x = n; compute p(x) + tau(x).",
        template="(let 0 {n} (merge (p (ref 0)) (tau (ref 0))))",
        tests=(({"n": 6}, 15), ({"n": 5}, 9), ({"n": 10}, 46)),
        tags=("let-ref", "composition"),
    ),
    Task(
        id="pb52",
        name="let_bound_to_expr_gcd",
        prompt=("Let x = gcd(a, b); compute p(x) + tau(x). Binding must "
                "hold the computed expression, not a literal."),
        template=("(let 0 (gcd {a} {b}) (merge (p (ref 0)) "
                  "(tau (ref 0))))"),
        tests=(({"a": 12, "b": 18}, 15),
               ({"a": 6, "b": 10}, 4),
               ({"a": 4, "b": 9}, 2)),
        tags=("let-ref", "composition", "binary"),
    ),
    Task(
        id="pb53",
        name="let_gcd_sigma_tau",
        prompt="Let x = n; return gcd(sigma(x), tau(x)).",
        template="(let 0 {n} (gcd (sigma (ref 0)) (tau (ref 0))))",
        tests=(({"n": 6}, 4), ({"n": 12}, 2), ({"n": 10}, 2)),
        tags=("let-ref", "composition"),
    ),
    Task(
        id="pb54",
        name="let_p_plus_tau_of_p",
        prompt="Let x = p(n); return x + tau(x).",
        template="(let 0 (p {n}) (merge (ref 0) (tau (ref 0))))",
        tests=(({"n": 5}, 9), ({"n": 10}, 50), ({"n": 12}, 81)),
        tags=("let-ref", "composition"),
    ),
    Task(
        id="pb55",
        name="nested_lets",
        prompt=("Let x = n; let y = tau(x); return x + y. Tests nested "
                "let-bindings."),
        template=("(let 0 {n} (let 1 (tau (ref 0)) (merge (ref 0) "
                  "(ref 1))))"),
        tests=(({"n": 6}, 10), ({"n": 10}, 14), ({"n": 12}, 18)),
        tags=("let-ref", "nested", "composition"),
    ),
    Task(
        id="pb56",
        name="nested_lets_binary",
        prompt=("Let x = a; let y = b; return gcd(sigma(x), tau(y))."),
        template=("(let 0 {a} (let 1 {b} (gcd (sigma (ref 0)) "
                  "(tau (ref 1)))))"),
        tests=(({"a": 6, "b": 10}, 4),
               ({"a": 12, "b": 18}, 2),
               ({"a": 4, "b": 9}, 1)),
        tags=("let-ref", "nested", "binary"),
    ),
    Task(
        id="pb57",
        name="let_double_sigma",
        prompt=("Let x = sigma(n); return x + x. Tests referring to the "
                "same let-binding twice."),
        template="(let 0 (sigma {n}) (merge (ref 0) (ref 0)))",
        tests=(({"n": 6}, 24), ({"n": 12}, 56), ({"n": 10}, 36)),
        tags=("let-ref", "re-use"),
    ),
    Task(
        id="pb58",
        name="let_gcd_of_sigmas",
        prompt=("Let x = sigma(a); let y = sigma(b); return gcd(x, y). "
                "Nested lets, each bound to an expression."),
        template=("(let 0 (sigma {a}) (let 1 (sigma {b}) "
                  "(gcd (ref 0) (ref 1))))"),
        tests=(({"a": 6, "b": 10}, 6),
               ({"a": 12, "b": 18}, 1),
               ({"a": 4, "b": 9}, 1)),
        tags=("let-ref", "nested", "binary"),
    ),
    Task(
        id="pb59",
        name="let_p_plus_sigma",
        prompt="Let x = n; return p(x) + sigma(x).",
        template="(let 0 {n} (merge (p (ref 0)) (sigma (ref 0))))",
        tests=(({"n": 6}, 23), ({"n": 5}, 13), ({"n": 10}, 60)),
        tags=("let-ref", "composition"),
    ),
    Task(
        id="pb60",
        name="let_p_of_sum",
        prompt="Let x = a + b; return p(x).",
        template="(let 0 (merge {a} {b}) (p (ref 0)))",
        tests=(({"a": 2, "b": 3}, 7),
               ({"a": 3, "b": 5}, 22),
               ({"a": 4, "b": 4}, 22)),
        tags=("let-ref", "binary"),
    ),
)


# --- sanity -----------------------------------------------------------------

assert len(TASKS) == 60, f"LOVABench v2 must have exactly 60 tasks, got {len(TASKS)}"
assert len({t.id for t in TASKS}) == 60, "task ids must be unique"


# --- LOVABench v3: the algorithmic category (61-80) ------------------------
#
# Q33 (raised by Exp 12): every task above predates M9, so the benchmark
# could not see recursion, iteration, lists or text, and a corpus drawn
# from it would teach a sublanguage of straight-line arithmetic.  These
# twenty need a `def`, a loop or a list; their prompts say what to
# compute and not how, so a solver has to synthesise rather than
# transcribe (Exp 13 F3).  The prelude is in scope: a solution may use
# `range`, `map`, `filter`, `fold`, `digits`, `text-of` and the rest,
# as a program would.  Reference solutions are hand-written and
# validate; `tests/test_lovabench.py` keeps that true.

ALGORITHMIC: Tuple[Task, ...] = (
    Task(
        id="pb61",
        name="factorial",
        prompt="Given an integer n >= 0, return n factorial.",
        template="(def fact [n] (if n (mul n (fact (sub n 1))) 1))(fact {n})",
        tests=(({"n": 0}, 1), ({"n": 5}, 120), ({"n": 10}, 3628800)),
        tags=("algorithmic", "recursion", "primitive-recursion"),
    ),
    Task(
        id="pb62",
        name="fibonacci",
        prompt="Given an integer n >= 0, return the n-th Fibonacci number, with F(0) = 0 and F(1) = 1.",
        template="(def fib [n] (if (lt n 2) n (merge (fib (sub n 1)) (fib (sub n 2)))))(fib {n})",
        tests=(({"n": 0}, 0), ({"n": 7}, 13), ({"n": 15}, 610)),
        tags=("algorithmic", "recursion", "tree-recursion"),
    ),
    Task(
        id="pb63",
        name="is_prime",
        prompt="Given an integer n, return 1 if n is prime and 0 otherwise.",
        template=("(def check [d n] (if (gt (mul d d) n) 1 (if (mod n d) (check (inc d) n) 0)))"
                  "(def prime? [n] (if (lt n 2) 0 (check 2 n)))(prime? {n})"),
        tests=(({"n": 1}, 0), ({"n": 97}, 1), ({"n": 561}, 0)),
        tags=("algorithmic", "loop", "early-exit"),
    ),
    Task(
        id="pb64",
        name="collatz_steps",
        prompt="Given an integer n >= 1, return how many Collatz steps (halve if even, else 3n+1) it takes to reach 1.",
        template=("(def next [n] (if (mod n 2) (merge (mul 3 n) 1) (div n 2)))"
                  "(def steps [n acc] (if (eq n 1) acc (steps (next n) (inc acc))))(steps {n} 0)"),
        tests=(({"n": 1}, 0), ({"n": 6}, 8), ({"n": 27}, 111)),
        tags=("algorithmic", "loop", "accumulator"),
    ),
    Task(
        id="pb65",
        name="sum_to",
        prompt="Given an integer n >= 0, return the sum 1 + 2 + ... + n.",
        template="(sum (range 1 (inc {n})))",
        tests=(({"n": 0}, 0), ({"n": 10}, 55), ({"n": 100}, 5050)),
        tags=("algorithmic", "list", "library"),
    ),
    Task(
        id="pb66",
        name="power",
        prompt="Given integers b and e >= 0, return b raised to the power e.",
        template="(def power [b e] (if e (mul b (power b (sub e 1))) 1))(power {b} {e})",
        tests=(({"b": 2, "e": 10}, 1024), ({"b": 3, "e": 0}, 1), ({"b": 5, "e": 3}, 125)),
        tags=("algorithmic", "recursion", "binary"),
    ),
    Task(
        id="pb67",
        name="gcd_euclid",
        prompt="Given integers a and b, return their greatest common divisor by Euclid's algorithm, without the gcd operator.",
        template="(def euclid [a b] (if b (euclid b (mod a b)) a))(euclid {a} {b})",
        tests=(({"a": 12, "b": 18}, 6), ({"a": 270, "b": 192}, 6), ({"a": 0, "b": 5}, 5)),
        tags=("algorithmic", "recursion", "binary"),
    ),
    Task(
        id="pb68",
        name="count_divisors_loop",
        prompt="Given an integer n >= 1, return the number of its divisors, counted by trying every candidate from 1 to n.",
        template="(len (filter (lambda d (not (mod {n} d))) (range 1 (inc {n}))))",
        tests=(({"n": 1}, 1), ({"n": 12}, 6), ({"n": 28}, 6)),
        tags=("algorithmic", "list", "filter"),
    ),
    Task(
        id="pb69",
        name="digit_sum",
        prompt="Given an integer n >= 0, return the sum of its decimal digits.",
        template="(sum (digits {n}))",
        tests=(({"n": 0}, 0), ({"n": 1234}, 10), ({"n": 99999}, 45)),
        tags=("algorithmic", "list", "library"),
    ),
    Task(
        id="pb70",
        name="reverse_digits",
        prompt="Given an integer n >= 0, return the integer whose decimal digits are those of n in reverse order.",
        template=("(def rev [n acc] (if n (rev (div n 10) (merge (mul acc 10) (mod n 10))) acc))"
                  "(rev {n} 0)"),
        tests=(({"n": 1234}, 4321), ({"n": 1200}, 21), ({"n": 7}, 7)),
        tags=("algorithmic", "loop", "accumulator"),
    ),
    Task(
        id="pb71",
        name="sum_of_squares",
        prompt="Given an integer n >= 1, return the sum of the squares of 1 to n.",
        template="(sum (map (lambda k (mul k k)) (range 1 (inc {n}))))",
        tests=(({"n": 1}, 1), ({"n": 3}, 14), ({"n": 10}, 385)),
        tags=("algorithmic", "list", "map"),
    ),
    Task(
        id="pb72",
        name="primes_below",
        prompt="Given an integer n, return how many primes are smaller than n.",
        template=("(def check [d n] (if (gt (mul d d) n) 1 (if (mod n d) (check (inc d) n) 0)))"
                  "(def prime? [n] (if (lt n 2) 0 (check 2 n)))"
                  "(len (filter prime? (range 2 {n})))"),
        tests=(({"n": 10}, 4), ({"n": 30}, 10), ({"n": 100}, 25)),
        tags=("algorithmic", "list", "filter", "composition"),
    ),
    Task(
        id="pb73",
        name="largest_digit",
        prompt="Given an integer n >= 0, return its largest decimal digit.",
        template="(fold (lambda a (lambda b (max a b))) 0 (digits {n}))",
        tests=(({"n": 1234}, 4), ({"n": 907}, 9), ({"n": 5}, 5)),
        tags=("algorithmic", "list", "fold"),
    ),
    Task(
        id="pb74",
        name="binary_ones",
        prompt="Given an integer n >= 0, return the number of 1 bits in its binary representation.",
        template="(def ones [n] (if n (merge (mod n 2) (ones (div n 2))) 0))(ones {n})",
        tests=(({"n": 0}, 0), ({"n": 255}, 8), ({"n": 1000}, 6)),
        tags=("algorithmic", "recursion"),
    ),
    Task(
        id="pb75",
        name="palindrome_number",
        prompt="Given an integer n >= 0, return 1 if its decimal digits read the same backwards and 0 otherwise.",
        template="(same (digits {n}) (reverse (digits {n})))",
        tests=(({"n": 121}, 1), ({"n": 123}, 0), ({"n": 7}, 1)),
        tags=("algorithmic", "list", "library"),
    ),
    Task(
        id="pb76",
        name="floor_log2",
        prompt="Given an integer n >= 1, return how many times n can be halved (rounding down) before it is smaller than 2.",
        template="(def lg [n] (if (lt n 2) 0 (inc (lg (div n 2)))))(lg {n})",
        tests=(({"n": 1}, 0), ({"n": 8}, 3), ({"n": 1000}, 9)),
        tags=("algorithmic", "recursion"),
    ),
    Task(
        id="pb77",
        name="is_perfect_by_loop",
        prompt="Given an integer n >= 1, return 1 if n equals the sum of its proper divisors (those smaller than n) and 0 otherwise.",
        template="(eq {n} (sum (filter (lambda d (not (mod {n} d))) (range 1 {n}))))",
        tests=(({"n": 6}, 1), ({"n": 28}, 1), ({"n": 12}, 0)),
        tags=("algorithmic", "list", "filter"),
    ),
    Task(
        id="pb78",
        name="count_multiples",
        prompt="Given an integer n >= 1, return how many integers from 1 to n are divisible by 3 or by 5.",
        template="(len (filter (lambda k (or (not (mod k 3)) (not (mod k 5)))) (range 1 (inc {n}))))",
        tests=(({"n": 10}, 5), ({"n": 15}, 7), ({"n": 100}, 47)),
        tags=("algorithmic", "list", "filter"),
    ),
    Task(
        id="pb79",
        name="decimal_length",
        prompt="Given an integer n >= 0, return the number of characters in its decimal representation.",
        template="(len (text-of {n}))",
        tests=(({"n": 0}, 1), ({"n": 12345}, 5), ({"n": 1000000}, 7)),
        tags=("algorithmic", "text", "library"),
    ),
    Task(
        id="pb80",
        name="sorted_digits",
        prompt="Given an integer n >= 0, return the integer formed by its decimal digits sorted in ascending order (a leading zero disappears).",
        template="(fold (lambda a (lambda d (merge (mul a 10) d))) 0 (sort (digits {n})))",
        tests=(({"n": 3142}, 1234), ({"n": 5}, 5), ({"n": 909}, 99)),
        tags=("algorithmic", "list", "sort", "fold"),
    ),
)

# LOVABench v3 = v2 + the algorithmic category.  ``TASKS`` stays v2 so
# that Exp 03 / 07 / 11 measure what they measured; v3 is what a
# fine-tune (M8) trains on and is judged by.
TASKS_V3: Tuple[Task, ...] = TASKS + ALGORITHMIC

assert len(TASKS_V3) == 80, f"LOVABench v3 must have exactly 80 tasks, got {len(TASKS_V3)}"
assert len({t.id for t in TASKS_V3}) == 80, "task ids must be unique"


def by_id(task_id: str) -> Task:
    for t in TASKS_V3:
        if t.id == task_id:
            return t
    raise KeyError(f"unknown task id: {task_id}")
