"""M23 -- the evaluator compiles a tree to closures.

What these tests pin is not speed but the properties the change could
have broken: trap positions read off the Python stack instead of a
node stack, frames chained instead of copied, the binding-group token
instead of a per-node flag, and a per-run compile cache.  Every
expected value here was recorded on the M22 tree walker first.
"""

from __future__ import annotations

import unittest

from core.conservation import BudgetTrap, DomainTrap
from core.runtime import Runtime, Scope, evaluate, flatten_env
from core.surface import parse
from core.tokens import LIT_INT, Node


def _run(src: str, **kw):
    rt = Runtime(**kw)
    try:
        return evaluate(parse(src), rt)
    except (BudgetTrap, DomainTrap) as trap:
        a = trap.anomaly
        return (a["kind"], a.get("position_path"), a.get("offending_op"),
                a.get("detail", {}).get("bound_names"))


class TrapPositions(unittest.TestCase):
    """`_node_path` reproduces the node stack, innermost node last."""

    def test_budget_trap_names_the_node_that_overran(self):
        self.assertEqual(_run("(merge 1 (budget 1 (merge 1 1)))"),
                         ("budget-exceeded", (3, 16, 3), 3, None))

    def test_step_trap_is_enriched_at_the_node_that_crossed(self):
        self.assertEqual(_run("(merge 1 (merge 1 (merge 1 1)))", max_steps=3),
                         ("step-limit-exceeded", (3, 3), 3, None))

    def test_depth_trap_path_is_one_apply_per_frame(self):
        kind, path, op, _ = _run(
            "(let 0 (lambda 1 (apply (ref 0) (ref 1))) (apply (ref 0) 0))",
            max_call_depth=5)
        self.assertEqual(kind, "recursion-depth-exceeded")
        self.assertEqual(path, (46, 45, 45, 45, 45, 45, 45))
        self.assertEqual(op, 45)

    def test_a_literal_takes_no_position(self):
        # A step trap raised by a literal is enriched by its parent, as
        # it was when literals took no frame on the node stack.
        self.assertEqual(_run("(merge 1 1)", max_steps=2),
                         ("step-limit-exceeded", (3,), 3, None))


class Frames(unittest.TestCase):
    """Chained frames behave as the copied dicts did."""

    def test_shadowing_an_outer_name_in_a_group_opens_a_frame(self):
        # `f` is built in a group that then rebinds 1, which is bound
        # outside the group: the rebinding must not reach `f`.
        src = ("(let 1 10 (apply (lambda 0 (let 2 (lambda 9 (ref 1)) "
               "(let 1 20 (apply (ref 2) 0)))) 0))")
        self.assertEqual(_run(src), 10)

    def test_a_let_in_argument_position_does_not_leak(self):
        # A domain trap carries its position too, since M24.
        self.assertEqual(_run("(let 0 1 (seq (let 1 2 0) (ref 1)))"),
                         ("unbound-ref", (46, 40, 47), 47, [0]))

    def test_a_let_in_a_loop_body_opens_a_fresh_frame_each_round(self):
        # The step's LET runs once per round; its binding must not
        # accumulate in, or chain onto, the frame of the previous one.
        src = ("(apply (loop-until (lambda 0 (threshold (deviation (ref 0) 4)))"
               " (lambda 0 (let 1 (merge (ref 0) 1) (ref 1)))) 0)")
        self.assertEqual(_run(src), 5)

    def test_unbound_ref_lists_names_from_every_frame(self):
        self.assertEqual(_run("(let 5 1 (apply (lambda 6 (ref 7)) 0))"),
                         ("unbound-ref", (46, 45, 47), 47, [5, 6]))

    def test_mutual_recursion_still_shares_one_frame(self):
        src = ("(let 0 (lambda 2 (if-surprise (ref 2) (apply (ref 1) "
               "(deviation (ref 2) 1)) 1)) "
               "(let 1 (lambda 3 (if-surprise (ref 3) (apply (ref 0) "
               "(deviation (ref 3) 1)) 0)) (apply (ref 0) 7)))")
        self.assertEqual(_run(src), 0)   # even(7) through odd/even

    def test_scope_in_is_local_and_bound_walks_the_chain(self):
        root = {1: "a"}
        inner = Scope.open(root)
        inner[2] = "b"
        leaf = Scope.open(inner)
        self.assertIn(2, inner)
        self.assertNotIn(2, leaf)
        self.assertTrue(leaf.bound(2))
        self.assertTrue(leaf.bound(1))
        self.assertFalse(leaf.bound(3))
        self.assertEqual(leaf[1], "a")
        with self.assertRaises(KeyError):
            leaf[3]

    def test_flatten_env_inner_wins(self):
        root = {1: "outer", 2: "kept"}
        inner = Scope.open(root)
        inner[1] = "inner"
        self.assertEqual(flatten_env(inner), {1: "inner", 2: "kept"})


class CompileCache(unittest.TestCase):
    """The cache belongs to a run: an edited tree meets fresh closures."""

    def test_in_place_edit_between_runs_is_seen(self):
        tree = parse("(merge 1 2)")
        rt = Runtime()
        self.assertEqual(evaluate(tree, rt), 3)
        tree.args[1] = Node(op=LIT_INT, args=[40])
        self.assertEqual(evaluate(tree, rt), 41)
        self.assertEqual(evaluate(tree, Runtime()), 41)

    def test_closures_carry_their_code_across_runtimes(self):
        # A function value built under one runtime is applied under
        # another: the code is the body's, not the runtime's.
        fn = evaluate(parse("(lambda 0 (merge (ref 0) 1))"))
        self.assertEqual(evaluate(parse("(apply (ref 9) 41)"),
                                  Runtime(env={9: fn})), 42)

    def test_step_count_is_unchanged_by_compilation(self):
        # Same accounting as the tree walker: one step per node.
        rt = Runtime()
        evaluate(parse("(let 0 (lambda 1 (merge (ref 1) 1)) (apply (ref 0) 2))"), rt)
        self.assertEqual(rt.steps, 8)      # recorded on the M22 walker


class BigStack(unittest.TestCase):
    """The PyPy path -- a run on a thread with a sized stack -- taken
    on CPython too, so the suite exercises it wherever it runs."""

    def setUp(self):
        import core.runtime as R
        self._was = R._NEEDS_BIG_STACK
        R._NEEDS_BIG_STACK = True

    def tearDown(self):
        import core.runtime as R
        R._NEEDS_BIG_STACK = self._was

    def test_a_value_comes_back(self):
        self.assertEqual(_run("(merge 20 22)"), 42)

    def test_a_trap_crosses_the_thread(self):
        self.assertEqual(_run("(merge 1 (merge 1 1))", max_steps=2),
                         ("step-limit-exceeded", (3, 3), 3, None))

    def test_deep_recursion_runs(self):
        src = ("(let 0 (lambda 1 (if-surprise (ref 1) (merge 1 (apply (ref 0) "
               "(deviation (ref 1) 1))) 0)) (apply (ref 0) 3000))")
        self.assertEqual(_run(src, max_call_depth=4000), 3000)

    def test_a_nested_run_stays_on_its_thread(self):
        # `evolve` and the populations evaluate programs from inside a
        # run; the guard keeps them on the thread they are already on
        # rather than nesting a thread per run.
        import core.runtime as R
        calls = []
        original = R._evaluate_on_big_stack
        R._evaluate_on_big_stack = lambda node, rt: calls.append(1) or original(node, rt)
        try:
            self.assertEqual(_run("(merge 1 1)"), 2)
            self.assertEqual(len(calls), 1)
            R._big_stack.on = True                # as inside a worker
            try:
                self.assertEqual(_run("(merge 2 2)"), 4)
            finally:
                R._big_stack.on = False
            self.assertEqual(len(calls), 1)       # no second thread
        finally:
            R._evaluate_on_big_stack = original

if __name__ == "__main__":
    unittest.main()
