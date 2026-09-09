"""Tests for M21 — the network, as datagrams, under the boundary.

``net-send`` (0x31) sends one UDP datagram to ``"host:port"`` and yields
the bytes sent; ``net-recv`` (0x32) yields the next datagram on the
granted listening port, or ``nil`` on timeout.  Both need the ``net``
capability in the enclosing boundary; the *places* are the host's to
name (``--allow net=host:port`` to send there, ``net=:port`` to
listen), so an address that was not granted is a capability fault
even inside a granting boundary.  Where lives in host policy, not in
the byte sequence (Q69).

Every exchange here is on the loopback interface, and a receive uses a
socket the test bound and filled beforehand, so nothing races.
"""

from __future__ import annotations

import socket
import unittest

from core.cli import parse_allow, parse_net_allow
from core.compiler import CompileError, compile
from core.conservation import DomainTrap
from core.generator import GenState
from core.observability import static_analyze
from core.runtime import NIL_VALUE, Runtime, evaluate, list_to_python
from core.surface import parse
from core.tokens import (
    CAPABILITY_BITS, EXTERNAL_BOUNDARY, LIT_INT, NET_RECV, NET_SEND, SIGNATURES,
    TYPED_TOKENS, decode, encode,
)
from core.types import INT, LIST


def run(src: str, **runtime_kw):
    return evaluate(compile(parse(src))[0], Runtime(**runtime_kw))


def text(value) -> str:
    return "".join(chr(c) for c in list_to_python(value))


def loopback_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2)
    return sock, sock.getsockname()[1]


class TestSlots(unittest.TestCase):

    def test_the_network_activated_its_own_slots(self):
        self.assertEqual(SIGNATURES[0x31]["name"], "net-send")
        self.assertEqual(SIGNATURES[0x32]["name"], "net-recv")
        self.assertIn(NET_SEND, TYPED_TOKENS)
        self.assertIn(NET_RECV, TYPED_TOKENS)
        self.assertEqual(SIGNATURES[NET_SEND]["arity"], 2)

    def test_effects_are_declared_and_receiving_is_non_deterministic(self):
        analysis = static_analyze(parse('(boundary "net" (net-recv))'))
        self.assertIn("net-recv", analysis.effects)
        self.assertFalse(analysis.is_deterministic)
        sent = static_analyze(parse('(boundary "net" (net-send "a:1" 1))'))
        self.assertIn("net-send", sent.effects)

    def test_the_bytes_round_trip(self):
        tree = parse('(boundary "net" (net-send "127.0.0.1:9" (net-recv)))')
        self.assertEqual(decode(encode(tree)), tree)


class TestDeclaration(unittest.TestCase):

    def test_the_network_needs_its_bit(self):
        with self.assertRaises(CompileError):
            compile(parse('(net-send "127.0.0.1:9" 1)'))
        with self.assertRaises(CompileError):
            compile(parse('(boundary "fs-read" (net-recv))'))
        compile(parse('(boundary "net" (net-send "127.0.0.1:9" (net-recv)))'))

    def test_nothing_is_granted_by_default(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(boundary "net" (net-recv))')
        self.assertEqual(ctx.exception.anomaly["detail"]["missing"], ["net"])

    def test_the_generator_offers_it_only_inside(self):
        self.assertNotIn(NET_RECV, GenState.fresh(LIST).valid_next())
        inside = GenState.fresh(LIST).step(EXTERNAL_BOUNDARY).step(LIT_INT, CAPABILITY_BITS["net"])
        self.assertIn(NET_RECV, inside.valid_next())
        self.assertNotIn(NET_RECV, GenState.fresh(INT).step(EXTERNAL_BOUNDARY)
                         .step(LIT_INT, CAPABILITY_BITS["net"]).valid_next())


class TestSend(unittest.TestCase):

    def setUp(self):
        self.sock, self.port = loopback_socket()
        self.addr = f"127.0.0.1:{self.port}"

    def tearDown(self):
        self.sock.close()

    def test_a_datagram_arrives(self):
        sent = run(f'(boundary "net" (net-send "{self.addr}" "hello"))',
                   granted=8, net_send_to={self.addr})
        self.assertEqual(sent, 5)
        self.assertEqual(self.sock.recvfrom(100)[0], b"hello")

    def test_an_integer_is_sent_as_digits(self):
        run(f'(boundary "net" (net-send "{self.addr}" 42))', granted=8, net_send_to={self.addr})
        self.assertEqual(self.sock.recvfrom(100)[0], b"42")

    def test_bytes_not_codepoints_are_counted(self):
        sent = run(f'(boundary "net" (net-send "{self.addr}" (list 233)))',
                   granted=8, net_send_to={self.addr})
        self.assertEqual(sent, 2)                              # é is two bytes
        self.assertEqual(self.sock.recvfrom(100)[0].decode("utf-8"), "é")

    def test_a_place_that_was_not_granted_is_refused(self):
        with self.assertRaises(DomainTrap) as ctx:
            run(f'(boundary "net" (net-send "{self.addr}" "x"))',
                granted=8, net_send_to={"10.0.0.1:1"})
        anomaly = ctx.exception.anomaly
        self.assertEqual(anomaly["kind"], "capability-denied")
        self.assertEqual(anomaly["detail"]["address"], self.addr)

    def test_a_wildcard_grants_any_place(self):
        run(f'(boundary "net" (net-send "{self.addr}" "x"))', granted=8, net_send_to={"*"})
        self.assertEqual(self.sock.recvfrom(100)[0], b"x")

    def test_a_malformed_address_is_a_domain_error(self):
        for bad in ('"nowhere"', '":5"', '"host:notaport"', '"host:70000"'):
            with self.subTest(address=bad):
                with self.assertRaises(DomainTrap) as ctx:
                    run(f'(boundary "net" (net-send {bad} "x"))', granted=8, net_send_to={"*"})
                self.assertEqual(ctx.exception.anomaly["kind"], "domain-error")

    def test_the_fault_is_catchable(self):
        self.assertEqual(
            run(f'(boundary "net" (try (net-send "{self.addr}" "x") -1))',
                granted=8, net_send_to=set()),
            -1)


class TestReceive(unittest.TestCase):

    def setUp(self):
        self.sock, self.port = loopback_socket()
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def tearDown(self):
        self.sock.close()
        self.sender.close()

    def _runtime(self, timeout=2.0):
        return dict(granted=8, net_listen_on={self.port},
                    net_sockets={self.port: self.sock}, net_timeout=timeout)

    def test_a_queued_datagram_is_received(self):
        self.sender.sendto(b"ping", ("127.0.0.1", self.port))
        self.assertEqual(text(run('(boundary "net" (net-recv))', **self._runtime())), "ping")

    def test_datagrams_arrive_in_order(self):
        for word in (b"a", b"b"):
            self.sender.sendto(word, ("127.0.0.1", self.port))
        got = run('(boundary "net" (cons (net-recv) (cons (net-recv) (nil))))', **self._runtime())
        self.assertEqual([text(x) for x in list_to_python(got)], ["a", "b"])

    def test_silence_is_nil_not_a_hang(self):
        self.assertIs(run('(boundary "net" (net-recv))', **self._runtime(timeout=0.1)), NIL_VALUE)
        self.assertEqual(run('(boundary "net" (nil? (net-recv)))', **self._runtime(timeout=0.1)), 1)

    def test_no_listening_port_is_a_capability_fault(self):
        with self.assertRaises(DomainTrap) as ctx:
            run('(boundary "net" (net-recv))', granted=8, net_listen_on=set())
        self.assertEqual(ctx.exception.anomaly["kind"], "capability-denied")

    def test_a_reply_can_be_sent_back(self):
        # Echo: receive, send to the granted place.
        rx, rx_port = loopback_socket()
        try:
            self.sender.sendto(b"echo me", ("127.0.0.1", self.port))
            addr = f"127.0.0.1:{rx_port}"
            run(f'(boundary "net" (net-send "{addr}" (net-recv)))',
                net_send_to={addr}, **self._runtime())
            self.assertEqual(rx.recvfrom(100)[0], b"echo me")
        finally:
            rx.close()


class TestGrants(unittest.TestCase):

    def test_net_is_granted_by_place(self):
        self.assertEqual(parse_allow(["net=127.0.0.1:9000"]), CAPABILITY_BITS["net"])
        self.assertEqual(parse_net_allow(["net=127.0.0.1:9000,net=:7000"]),
                         ({"127.0.0.1:9000"}, {7000}))
        self.assertEqual(parse_net_allow(["net=*"]), ({"*"}, set()))
        self.assertEqual(parse_net_allow(["clock"]), (set(), set()))

    def test_all_does_not_include_the_network(self):
        self.assertFalse(parse_allow(["all"]) & CAPABILITY_BITS["net"])

    def test_a_place_must_be_a_place(self):
        with self.assertRaises(ValueError):
            parse_net_allow(["net=nowhere"])
        with self.assertRaises(ValueError):
            parse_allow(["net"])


if __name__ == "__main__":
    unittest.main()
