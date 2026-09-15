"""The pending stack, not the alphabet (Q108).

Experiment 24 put four sessions in front of the generation state
machine with, at every position, the set of tokens it would accept.
All four ignored it, and all four -- asked afterwards what they would
have wanted instead -- described the same thing in the same words: not
which tokens are legal, but **which forms are open, which operator owns
each, how much each still owes, and whether the variadic in front of
you may be closed here**.  One had been using the valid-token list as a
checksum on its own arity arithmetic, which is the same request from
the other side.

The machine already held all of it.  These tests are about whether it
now says it, and says it correctly in the places where saying it wrong
would be worse than silence: two forms of the same operator nested in
each other, a variadic that may or may not be closed, and a slot that
names a binding rather than holding a value.

What these tests do *not* do is answer whether the rendering helps.
That is the other half of Q108 -- re-run Exp 24 with it -- and it needs
fresh sessions, the way Exp 19 to 24 were run.
"""

from __future__ import annotations

import unittest

from core.generator import GenState, open_forms, pending, render_pending
from core.tokens import END, LIT_INT, NAME_TO_TOKEN
from core.types import INT, VALUE

OP = NAME_TO_TOKEN


def walk(*steps, top=INT):
    """A state after a sequence of tokens; `(LIT_INT, n)` carries a payload."""
    state = GenState.fresh(top)
    for step in steps:
        if isinstance(step, tuple):
            state = state.step(step[0], payload=step[1])
        else:
            state = state.step(step)
    return state


class Shape(unittest.TestCase):

    def test_a_fresh_state_owes_one_expression(self):
        p = pending(GenState.fresh())
        self.assertEqual(p["debt"], 1)
        self.assertEqual(p["open"], [{"op": "program", "owes": 1,
                                      "types": ["Int"], "variadic": False}])
        self.assertFalse(p["may_close"])

    def test_an_operator_says_what_it_still_owes(self):
        p = pending(walk(OP["if-surprise"]))
        self.assertEqual(p["debt"], 3)
        self.assertEqual(p["open"][-1]["op"], "if-surprise")
        self.assertEqual(p["open"][-1]["owes"], 3)
        p = pending(walk(OP["if-surprise"], (LIT_INT, 1)))
        self.assertEqual(p["open"][-1]["owes"], 2)

    def test_the_types_are_in_the_order_they_will_be_filled(self):
        """The stack is filled from its top, so the list has to read the
        other way round from the way it is stored."""
        p = pending(walk(OP["if-surprise"], top=VALUE))
        self.assertEqual(p["open"][-1]["types"], ["Int", "Value", "Value"])
        self.assertEqual(p["next"]["type"], "Int")

    def test_forms_are_listed_outermost_first(self):
        p = pending(walk(OP["if-surprise"], (LIT_INT, 1), OP["merge"]))
        self.assertEqual([f["op"] for f in p["open"]], ["if-surprise", "merge"])
        self.assertEqual(p["next"]["in"], "merge")

    def test_two_of_the_same_operator_are_two_forms(self):
        """`(merge (merge ...) ...)`: all three outstanding slots say
        `parent_op = merge`, and the depth each form was opened at is what
        keeps them apart.  Reporting `merge:3` here would be worse than
        reporting nothing."""
        p = pending(walk(OP["merge"], OP["merge"]))
        self.assertEqual([(f["op"], f["owes"]) for f in p["open"]],
                         [("merge", 1), ("merge", 2)])
        p = pending(walk(OP["merge"], OP["merge"], (LIT_INT, 1)))
        self.assertEqual([(f["op"], f["owes"]) for f in p["open"]],
                         [("merge", 1), ("merge", 1)])

    def test_three_deep_of_the_same_operator(self):
        p = pending(walk(OP["merge"], OP["merge"], OP["merge"]))
        self.assertEqual([f["owes"] for f in p["open"]], [1, 1, 2])
        self.assertEqual(p["debt"], 4)


class Variadic(unittest.TestCase):
    """The cost Exp 24 named first: the one operator that does not
    self-terminate by arity."""

    def test_a_variadic_says_it_is_one_and_that_it_may_be_closed(self):
        p = pending(walk(OP["seq"]))
        self.assertTrue(p["open"][-1]["variadic"])
        self.assertTrue(p["may_close"])
        self.assertIn("`;` closes it here", p["render"])

    def test_it_stays_open_across_elements(self):
        one = pending(walk(OP["seq"], (LIT_INT, 7)))
        two = pending(walk(OP["seq"], (LIT_INT, 7), (LIT_INT, 8)))
        self.assertTrue(one["may_close"])
        self.assertEqual(one["open"], two["open"])

    def test_closing_it_takes_it_off_the_stack(self):
        before = pending(walk(OP["seq"], (LIT_INT, 7)))
        after = pending(walk(OP["seq"], (LIT_INT, 7), END))
        self.assertEqual([f["op"] for f in before["open"]], ["seq"])
        self.assertTrue(after["complete"])
        self.assertEqual(after["debt"], 0)

    def test_a_head_typed_variadic_does_not_claim_to_be_closeable_yet(self):
        """`apply` wants a function first and values after it; until the
        head is filled, `;` is not legal and the rendering must not say it
        is."""
        p = pending(walk(OP["apply"]))
        self.assertFalse(p["may_close"])
        self.assertNotIn("closes it here", p["render"])


class Names(unittest.TestCase):

    def test_a_binder_slot_says_so(self):
        p = pending(walk(OP["let"]))
        self.assertEqual(p["next"]["role"], "binder")
        self.assertIn("[binder]", p["render"])

    def test_a_reference_slot_carries_what_is_in_scope(self):
        state = walk(OP["let"], (LIT_INT, 0), (LIT_INT, 5), OP["ref"])
        p = pending(state)
        self.assertEqual(p["next"]["role"], "ref-name")
        self.assertEqual(p["next"]["names_in_scope"], [0])


class Debt(unittest.TestCase):
    """The checksum a session was computing by hand."""

    def test_the_debt_is_the_number_of_slots_outstanding(self):
        for steps in ((), (OP["merge"],), (OP["merge"], OP["merge"]),
                      (OP["if-surprise"], (LIT_INT, 1), OP["seq"])):
            state = walk(*steps)
            self.assertEqual(pending(state)["debt"], len(state.stack))

    def test_it_reaches_zero_exactly_when_the_program_is_complete(self):
        state = walk(OP["merge"], (LIT_INT, 1), (LIT_INT, 2))
        self.assertTrue(state.is_complete())
        p = pending(state)
        self.assertTrue(p["complete"])
        self.assertEqual(p["debt"], 0)
        self.assertEqual(p["render"], "complete")


class Rendering(unittest.TestCase):

    def test_it_is_two_lines_and_names_every_open_form(self):
        text = render_pending(walk(OP["if-surprise"], (LIT_INT, 1), OP["seq"]))
        first, second = text.split(chr(10))
        self.assertTrue(first.startswith("open  "))
        self.assertIn("if-surprise", first)
        self.assertIn("seq:variadic", first)
        self.assertTrue(second.startswith("next  "))
        self.assertIn("debt 2", second)

    def test_the_structured_form_and_the_rendering_agree(self):
        state = walk(OP["if-surprise"], (LIT_INT, 1), OP["merge"])
        p = pending(state)
        self.assertEqual(p["render"], render_pending(state))
        for form in p["open"]:
            self.assertIn(form["op"], p["render"])

    def test_open_forms_and_the_stack_account_for_each_other(self):
        """Every slot belongs to exactly one open form, whatever the shape."""
        for steps in ((OP["merge"], OP["merge"], OP["merge"]),
                      (OP["if-surprise"], (LIT_INT, 1), OP["seq"], (LIT_INT, 2)),
                      (OP["let"], (LIT_INT, 0), (LIT_INT, 5)),
                      (OP["apply"], OP["lambda"], (LIT_INT, 0))):
            state = walk(*steps)
            self.assertEqual(sum(f.owes for f in open_forms(state)), len(state.stack))


class ThroughTheServer(unittest.TestCase):
    """`lova_valid_next` is how a host asks; it answers with both now."""

    def test_the_tool_returns_the_pending_stack(self):
        from core.mcp_server import tool_valid_next
        out = tool_valid_next({"bytes": f"{OP['if-surprise']:02x}{OP['seq']:02x}"})
        self.assertTrue(out["ok"])
        p = out["pending"]
        self.assertEqual([f["op"] for f in p["open"]], ["if-surprise", "seq"])
        self.assertTrue(p["may_close"])
        self.assertIn("debt 3", p["render"])

    def test_a_complete_program_says_so(self):
        from core.mcp_server import tool_valid_next
        out = tool_valid_next({"bytes": f"{LIT_INT:02x}0101"})
        self.assertTrue(out["complete"])
        self.assertEqual(out["pending"]["debt"], 0)


if __name__ == "__main__":
    unittest.main()
