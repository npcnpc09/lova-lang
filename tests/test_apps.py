"""The apps as programs: each one run through the CLI on an input a
test can afford.  `apps/tictactoe.lova` starts from a given board, so
a test plays the last moves of a game rather than the first search,
which is eleven million steps."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest

from core.cli import main


def _run(argv, stdin_text=""):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
    finally:
        sys.stdin = saved
    return code, out.getvalue(), err.getvalue()


# Boards are base-3 integers: square k is digit k; 1 X, 2 O.
X_X_O_CENTRE = 1 + 3 + 2 * 81          # X X . / . O . / . . .
X___O_CENTRE = 1 + 2 * 81              # X . . / . O . / . . .


class TicTacToe(unittest.TestCase):

    def test_a_winning_move_is_announced(self):
        code, out, err = _run(["run", "apps/tictactoe.lova", str(X_X_O_CENTRE)], "3\n")
        self.assertEqual(code, 0)
        self.assertIn("X X X", out)
        self.assertIn("you win", out)
        self.assertIn("=> 1", err)

    def test_the_computer_blocks(self):
        code, out, err = _run(["run", "apps/tictactoe.lova", str(X___O_CENTRE)], "2\n")
        self.assertEqual(code, 0)
        self.assertIn("the computer plays 3", out)
        self.assertIn("X X O", out)

    def test_bad_input_is_asked_again_and_a_blank_line_quits(self):
        code, out, err = _run(["run", "apps/tictactoe.lova", str(X___O_CENTRE)],
                              "x\n9\n\n")
        self.assertEqual(code, 0)
        # "x" is asked again; "9" is a free square and is played; the
        # blank line is indistinguishable from end of input (Q78) and quits.
        self.assertEqual(out.count("pick the number"), 1)
        self.assertIn("bye", out)
        self.assertIn("=> 0", err)


class Guess(unittest.TestCase):
    """The secret comes off the clock, so a test guesses every number."""

    def test_every_number_finds_the_secret(self):
        code, out, err = _run(["run", "apps/guess.lova", "3", "--allow", "clock"],
                              "x\n1\n2\n3\n")
        self.assertEqual(code, 0)
        self.assertIn("a number, please", out)
        self.assertIn("yes, in", out)
        self.assertRegex(err, r"=> [123]\b")

    def test_the_clock_needs_a_grant(self):
        code, _out, err = _run(["run", "apps/guess.lova", "3"], "1\n")
        self.assertNotEqual(code, 0)
        self.assertIn("--allow clock", err)

    def test_a_blank_line_gives_up(self):
        code, out, err = _run(["run", "apps/guess.lova", "3", "--allow", "clock"], "\n")
        self.assertEqual(code, 0)
        self.assertIn("bye", out)
        self.assertIn("=> 0", err)


class LogStats(unittest.TestCase):

    def test_groups_sorts_and_skips_bad_lines(self):
        import os
        import tempfile
        log = ("api 200 100\napi 500 300\nweb 200 50\n"
               "not a record\napi 200 200\nweb 404 150\n")
        fd, path = tempfile.mkstemp(suffix=".log")
        with os.fdopen(fd, "w") as handle:
            handle.write(log)
        try:
            code, out, err = _run(["run", "apps/logstats.lova", path, "--allow", "fs-read"])
        finally:
            os.remove(path)
        self.assertEqual(code, 0)
        rows = [line.split() for line in out.splitlines()[1:]]
        # service, requests, mean-ms, max-ms, errors; most requests first
        self.assertEqual(rows, [["api", "3", "200", "300", "1"],
                                ["web", "2", "100", "150", "1"]])
        self.assertIn("=> 5", err)


class Sandbox(unittest.TestCase):

    PROGRAMS = ("(merge 1 2)\n"
                "(div 1 0)\n"
                "(apply (loop-until (lambda 0 0) (lambda 0 (ref 0))) 1)\n"
                "(merge 1\n"
                '(boundary "fs-read" (fs-read "x"))\n'
                "(def sq [n] (mul n n))(sq 12)\n")

    def test_every_line_is_reported_and_nothing_escapes(self):
        code, out, err = _run(["run", "apps/sandbox.lova", "5000"], self.PROGRAMS)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].endswith("=> 3"))
        self.assertEqual(lines[1], "fault: domain error")
        self.assertEqual(lines[2], "fault: budget exceeded")
        self.assertEqual(lines[3], "fault: not a program")
        self.assertEqual(lines[4], "fault: capability denied")
        self.assertTrue(lines[5].endswith("=> 144"))
        self.assertIn("=> 2", err)         # two lines produced a value


class Ping(unittest.TestCase):
    """`ping.lova` against a Python echo on a thread; `pong.lova` is the
    LOVA server, exercised by hand (journal M23) because two CLI
    processes are more than a unit test should start."""

    def test_a_datagram_goes_out_and_the_answer_comes_back(self):
        import socket
        import threading
        server, client = 39001, 39002
        ready = threading.Event()

        def echo():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", server))
            sock.settimeout(5)
            ready.set()
            try:
                data, _ = sock.recvfrom(1024)
                sock.sendto(b"pong " + data, ("127.0.0.1", client))
            finally:
                sock.close()

        worker = threading.Thread(target=echo, daemon=True)
        worker.start()
        ready.wait(2)
        code, out, err = _run(["run", "apps/ping.lova", f"127.0.0.1:{server}", "1",
                               "--allow", f"net=127.0.0.1:{server},net=:{client}"])
        worker.join(5)
        self.assertEqual(code, 0)
        self.assertIn("pong ping 1", out)
        self.assertIn("=> 1", err)


if __name__ == "__main__":
    unittest.main()
