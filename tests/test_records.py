"""Q84 -- records: named fields at zero slots.

`(rec x 1 y 2)`, `(get r x)` and `(put r x v)` are macros over the
persistent map with the field's name as a string key.  What they buy
is the end of `(nth st 2)`: a fold or a recursion that threads several
values names them.  A missing field is a signal (code 17) the program
can catch.
"""

from __future__ import annotations

import unittest

from core.compiler import compile as lova_compile
from core.conservation import DomainTrap
from core.runtime import Runtime, evaluate, is_map_value
from core.surface import parse, parse_with_prelude
from core.tokens import MAP_GET, MAP_PUT, NIL, SIGNAL


def _run(src: str):
    tree, _ = lova_compile(parse_with_prelude(src))
    return evaluate(tree, Runtime())


class Records(unittest.TestCase):

    def test_rec_get_put(self):
        self.assertEqual(_run("(get (rec x 1 y 2) y)"), 2)
        self.assertEqual(_run("(let r (rec best 0 move -1) (get (put r move 4) move))"), 4)
        self.assertEqual(_run("(let r (rec x 1) (get (put r x 9) x))"), 9)

    def test_put_keeps_the_old_record(self):
        # A record is a persistent map: the original is unchanged.
        self.assertEqual(_run("(let r (rec x 1) (let s (put r x 2) (merge (get r x) (mul 10 (get s x)))))"), 21)

    def test_a_record_is_a_map(self):
        self.assertTrue(is_map_value(_run("(rec a 1)")))
        self.assertEqual(_run("(map-size (rec a 1 b 2 c 3))"), 3)

    def test_a_field_may_be_a_string(self):
        self.assertEqual(_run('(get (rec x 1) "x")'), 1)
        self.assertEqual(_run('(get (put (rec) "k" 5) k)'), 5)

    def test_a_missing_field_is_a_signal_a_program_can_catch(self):
        with self.assertRaises(DomainTrap) as ctx:
            _run("(get (rec x 1) z)")
        self.assertEqual(ctx.exception.anomaly["kind"], "signalled")
        self.assertEqual(ctx.exception.anomaly["detail"]["code"], 17)
        self.assertEqual(_run("(try (get (rec x 1) z) 99)"), 99)

    def test_a_fold_threads_a_record(self):
        src = ("(get (fold (lambda st (lambda k (put st sum (merge (get st sum) k))))"
               " (rec sum 0 n 0) (range 1 5)) sum)")
        self.assertEqual(_run(src), 10)

    def test_the_field_name_is_not_a_reference(self):
        # `memo` is a field, not a variable: nothing needs to bind it.
        tree = parse("(get (rec memo 3) memo)")
        self.assertEqual(tree.op, MAP_GET)
        self.assertEqual(tree.args[2].op, SIGNAL)
        inner = tree.args[0]
        self.assertEqual(inner.op, MAP_PUT)
        self.assertEqual(inner.args[0].op, NIL)
        lova_compile(parse_with_prelude("(get (rec memo 3) memo)"))   # no unbound-ref

    def test_arity_errors_name_the_macro(self):
        with self.assertRaises(ValueError) as ctx:
            parse("(rec x)")
        self.assertIn("rec", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse("(get (rec x 1) (merge 1 2))")
        self.assertIn("get", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
