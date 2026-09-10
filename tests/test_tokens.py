"""Unit tests for ``core.tokens`` — encode / decode / signatures."""

from __future__ import annotations

import unittest

from core.tokens import (
    END, LIT_INT, P, TAU, MERGE, SIGNATURES, TYPED_TOKENS,
    Call, Lit, Node, decode, encode,
)


class TokenTableInvariants(unittest.TestCase):

    def test_exactly_64_signatures(self):
        self.assertEqual(len(SIGNATURES), 78)      # 64 core + 14 text (M25)

    def test_all_signatures_have_name_and_family(self):
        for tok, sig in SIGNATURES.items():
            self.assertIn("name", sig, f"token 0x{tok:02X} missing name")
            self.assertIn("family", sig, f"token 0x{tok:02X} missing family")

    def test_typed_tokens_are_subset_of_signatures(self):
        self.assertTrue(TYPED_TOKENS.issubset(set(SIGNATURES.keys())))

    def test_typed_tokens_have_out_type(self):
        for tok in TYPED_TOKENS:
            self.assertIsNotNone(SIGNATURES[tok].get("out_type"))


class EncodeDecodeRoundTrip(unittest.TestCase):
    """Encoding is lossless."""

    def _roundtrip(self, tree: Node) -> None:
        data = encode(tree)
        back = decode(data)
        self.assertEqual(tree, back,
                         f"round-trip mismatch:\n  in:  {tree}\n  out: {back}")

    def test_leaf_literal_zero(self):
        self._roundtrip(Lit(0))

    def test_leaf_literal_large(self):
        self._roundtrip(Lit(10 ** 12))

    def test_leaf_literal_negative(self):
        self._roundtrip(Lit(-12345))

    def test_simple_unary_call(self):
        self._roundtrip(Call("p", 12))

    def test_nested_binary_call(self):
        self._roundtrip(Call("merge", Call("p", 3), Call("tau", 12)))

    def test_variadic_seq_with_three_children(self):
        self._roundtrip(Call("seq", Call("p", 3), Call("p", 4), Call("p", 5)))

    def test_empty_seq(self):
        self._roundtrip(Call("seq"))

    def test_let_ref_composition(self):
        tree = Call("let", 0, 12, Call("p", Call("ref", 0)))
        self._roundtrip(tree)


class MalformedBytes(unittest.TestCase):
    """Decoding raises ValueError on every malformed input we can think of."""

    def test_empty_stream(self):
        with self.assertRaises(ValueError):
            decode(b"")

    def test_unknown_token(self):
        with self.assertRaises(ValueError):
            decode(bytes([0xFF]))

    def test_operator_missing_argument(self):
        with self.assertRaises(ValueError):
            decode(bytes([P]))

    def test_lit_missing_length(self):
        with self.assertRaises(ValueError):
            decode(bytes([LIT_INT]))

    def test_lit_truncated_payload(self):
        with self.assertRaises(ValueError):
            decode(bytes([LIT_INT, 0x04, 0x00]))

    def test_variadic_missing_end(self):
        # SEQ followed by a LIT_INT that's well-formed but no END.
        with self.assertRaises(ValueError):
            decode(bytes([0x28, LIT_INT, 0x01, 0x03]))

    def test_trailing_bytes(self):
        # A valid single expression followed by extra bytes.
        data = encode(Lit(7)) + b"\xff"
        with self.assertRaises(ValueError):
            decode(data)


class IntegerLiteralEncoding(unittest.TestCase):
    """LIT_INT payload round-trips signed big-endian integers of any size."""

    def test_standard_range(self):
        for v in [0, 1, -1, 127, 128, -128, 255, 256, -255]:
            with self.subTest(value=v):
                self.assertEqual(decode(encode(Lit(v))).args[0], v)

    def test_large_positive(self):
        for v in [2 ** 31, 2 ** 63 - 1, 10 ** 18]:
            with self.subTest(value=v):
                self.assertEqual(decode(encode(Lit(v))).args[0], v)

    def test_large_negative(self):
        for v in [-(2 ** 31), -(2 ** 63) + 1, -(10 ** 18)]:
            with self.subTest(value=v):
                self.assertEqual(decode(encode(Lit(v))).args[0], v)


if __name__ == "__main__":
    unittest.main()
