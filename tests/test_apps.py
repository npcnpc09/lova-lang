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

    def test_bad_input_and_a_blank_line_are_asked_again(self):
        code, out, err = _run(["run", "apps/tictactoe.lova", str(X___O_CENTRE)],
                              "x\n\n9\n")
        self.assertEqual(code, 0)
        # "x" and the blank line are asked again (Q78); "9" is a free
        # square and is played; the end of the input quits.
        self.assertEqual(out.count("pick the number"), 2)
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

    def test_the_end_of_input_gives_up_and_a_blank_line_does_not(self):
        code, out, err = _run(["run", "apps/guess.lova", "3", "--allow", "clock"], "\n")
        self.assertEqual(code, 0)
        self.assertIn("a number, please", out)        # the blank line (Q78)
        self.assertIn("bye", out)                     # then the end of input
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


class Batch(unittest.TestCase):

    def test_jobs_over_budget_are_caught_and_counted(self):
        # Python agrees: 219 of 1..300 reach 1 within the 2000-node budget.
        code, out, err = _run(["run", "apps/batch.lova", "300", "2000"])
        self.assertEqual(code, 0)
        self.assertIn("finished: 219", out)
        self.assertIn("over budget: 81", out)
        self.assertIn("=> 219", err)

    def test_arguments_may_be_named_in_any_order(self):
        # Q81: `name=value` fills the placeholder it names.
        code, out, _err = _run(["run", "apps/batch.lova", "cost=2000", "jobs=300"])
        self.assertEqual(code, 0)
        self.assertIn("finished: 219", out)

    def test_a_missing_argument_says_which(self):
        with self.assertRaises(SystemExit) as ctx:
            _run(["run", "apps/batch.lova", "jobs=300"])
        self.assertIn("cost", str(ctx.exception))


class Repair(unittest.TestCase):

    def test_the_patient_is_repaired_and_accounts_for_itself(self):
        code, out, err = _run(["run", "apps/repair.lova", "42", "30", "200"])
        self.assertEqual(code, 0)
        self.assertIn("patient: (merge (mul 6 9) 1)", out)
        self.assertIn("fixed: (merge (mul 4 8) 10)", out)      # 42, reproducibly
        self.assertIn("attempts: 39", out)
        self.assertIn("why: mutate", out)
        self.assertIn("=> 39", err)


class Evolve(unittest.TestCase):

    def test_the_pool_converges_and_the_winner_explains_itself(self):
        code, out, err = _run(["run", "apps/evolve.lova", "42", "60"])
        self.assertEqual(code, 0)
        self.assertIn("value: 42", out)
        self.assertIn("distance: 0", out)
        self.assertIn("winner: (", out)
        self.assertIn("=> 0", err)


class StageTwoRoundTrip(unittest.TestCase):
    """A real program projected to the Stage-2 surface runs identically."""

    def test_the_game_runs_from_its_projection(self):
        import os
        import tempfile
        args = ["apps/tictactoe.lova", str(X_X_O_CENTRE)]
        _code, want, want_err = _run(["run"] + args, "3\n")
        _code, projection, _ = _run(["emit"] + args + ["--form", "stage2"])
        self.assertNotIn("(", projection)
        fd, path = tempfile.mkstemp(suffix=".s2")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(projection)
        try:
            code, got, got_err = _run(["run", path, "--stage2"], "3\n")
        finally:
            os.remove(path)
        self.assertEqual(code, 0)
        self.assertEqual(got, want)
        self.assertIn("=> 1", got_err)


class PolicyShell(unittest.TestCase):
    """`apps/shell/policy_app.py`: a Python shell whose only decision is a
    LOVA rule.  The shell's one call into the language, without the
    HTTP around it."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        from pathlib import Path
        path = Path("apps/shell/policy_app.py")
        spec = importlib.util.spec_from_file_location("policy_app", path)
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)

    def test_the_default_rule_scores_a_purchase(self):
        r = self.app.run_rule(self.app.DEFAULT_RULE, {"amount": 12345, "tier": 2, "items": 6})
        self.assertTrue(r["ok"])
        self.assertEqual(r["value_int"], 296)          # 123 points, doubled, plus 50
        self.assertIn("digest", r)
        self.assertNotIn("(", r["projection"])

    def test_every_sabotage_is_a_structured_fault_and_the_shell_survives(self):
        expected = {"divide": "domain-error", "loop": "recursion-depth-exceeded",
                    "file": "capability-denied", "unbound": "unbound-ref"}
        for name, kind in expected.items():
            with self.subTest(name=name):
                r = self.app.run_rule(self.app.SABOTAGE[name], {"amount": 12345, "tier": 2, "items": 6})
                self.assertFalse(r["ok"])
                self.assertEqual(r["anomaly"]["kind"], kind)
                self.assertTrue(r["anomaly"].get("repair_hint"))


if __name__ == "__main__":
    unittest.main()
