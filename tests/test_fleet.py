"""The fleet policy, against the JavaScript it was taken from.

`lib/fleet.lova` carries two pieces of RemoteX's `src/mcp-server.js` and
`src/bridge.js`, and `Original` below is both of them transliterated:

  `resolveActiveToolNames` -- which of the 38 MCP tools a session
  advertises, given `REMOTEX_TOOLS` and `REMOTEX_TOOL_GROUPS`, plus the
  banner's `active/total` and `Math.round((1 - active/total) * 100)`.

  `healthCheck`'s parse -- `stdout.split(/___(\\w+)___/).filter(Boolean)`
  and the pairing loop that follows it.

Two details decide whether this test is worth anything.  JavaScript's
`\\w` is ASCII and Python's is Unicode, so the reference passes
`re.ASCII` or it would quietly be testing a different regular
expression.  And both engines are greedy with backtracking, so a marker
is the *longest* run of word characters with `___` after it -- which is
what `lib/fleet.lova` had to reproduce by hand, and what most of the
generated inputs below are built to probe.

The judgement -- what counts as unhealthy -- has no counterpart to test
against: RemoteX returns the five strings and lets the model decide.
Those tests state the policy instead.
"""

from __future__ import annotations

import io
import random
import re
import unittest

NL = chr(10)

from core.cli import build
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

API = """\
(use "fleet")
(rec act activation parse fields verdict verdict report fleet-report
     tools TOOLS groups group-names saving saving
     tenths tenths hundredths hundredths percent percent-tenths
     ratio ratio-tenths level level-of
     secs sections
     pairs (lambda m (map-pairs m))
     field (lambda r (lambda n (map-get r n 0)))
     texts (lambda r (lambda n (map-get r n ""))))
"""

TOOLS = [
    "ssh_exec", "ssh_exec_batch", "ssh_list_servers", "ssh_read_file", "ssh_search_code",
    "ssh_server_info", "ssh_health_check", "ssh_batch_health_check",
    "ssh_process_list", "ssh_docker_status", "ssh_network_info",
    "ssh_ports", "ssh_tail_log",
    "ssh_list_dir", "ssh_find_files", "ssh_stat_file", "ssh_mkdir",
    "ssh_write_file", "ssh_replace_in_file", "ssh_edit_block", "ssh_project_structure",
    "ssh_delete_file", "ssh_move_file", "ssh_copy_file",
    "ssh_upload_file", "ssh_download_file",
    "ssh_batch_read_file", "ssh_batch_write_file", "ssh_batch_replace_in_file",
    "ssh_diff_files", "ssh_batch_upload", "ssh_sync_file",
    "ssh_list_groups", "ssh_add_server", "ssh_remove_server",
    "ssh_import_servers", "ssh_clear_all_servers",
    "ssh_service",
]

GROUPS = {
    "core": TOOLS[0:5],
    "monitor": TOOLS[5:13],
    "fs": TOOLS[13:21],
    "fs-danger": TOOLS[21:24],
    "xfer": TOOLS[24:26],
    "batch": TOOLS[26:32],
    "admin": TOOLS[32:37],
    "service": TOOLS[37:38],
}


class Original:
    """`resolveActiveToolNames` and `healthCheck`'s parse, transliterated."""

    @staticmethod
    def active(indiv: str, groups: str):
        unknown = []
        one = indiv.strip()
        if one:
            names = {s.strip() for s in one.split(",") if s.strip()}
        else:
            raw = (groups or "").strip() or "core"
            if raw in ("all", "*"):
                names = set(TOOLS)
            else:
                names = set()
                for g in [s.strip() for s in raw.split(",") if s.strip()]:
                    if g in GROUPS:
                        names.update(GROUPS[g])
                    else:
                        unknown.append(g)
        active = [t for t in TOOLS if t in names]
        total = len(TOOLS)
        saving = round((1 - len(active) / total) * 100) if total else 0
        return active, unknown, saving

    @staticmethod
    def sections(out: str):
        return [s for s in re.split(r"___(\w+)___", out, flags=re.ASCII) if s]

    @classmethod
    def fields(cls, out: str):
        secs = cls.sections(out)
        info = {}
        for i in range(0, len(secs) - 1, 2):
            info[secs[i]] = secs[i + 1].strip()
        return info


HEALTH = ("___cpu___\n12.3\n___mem___\n3129/7823MB (40.0%)\n"
          "___disk___\n12G/40G (31%)\n___load___\n0.52 0.48 0.44\n"
          "___uptime___\nup 3 weeks, 2 days, 4 hours\n")


class Policy(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=50_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("act", "parse", "verdict", "report", "tools", "groups",
                            "saving", "tenths", "hundredths", "percent", "ratio",
                            "level", "secs", "pairs",
                            "field", "texts")}

    @classmethod
    def call(cls, name, *args):
        cls.rt.steps = 0
        fn = cls.fn[name]
        for arg in args:
            fn = _call(fn, arg, cls.rt)
        return fn

    @staticmethod
    def get(value, name):
        return value.entries[_map_key(name, "get")][1]

    def strings(self, value):
        return list_to_python(value)

    def activation(self, indiv, groups):
        r = self.call("act", indiv, groups)
        return (self.strings(self.get(r, "tools")),
                self.strings(self.get(r, "unknown")),
                self.get(r, "saving"))

    def parsed(self, out):
        pairs = list_to_python(self.call("pairs", self.call("parse", out)))
        return {list_to_python(p)[0]: list_to_python(p)[1] for p in pairs}

    # --- the tool table ------------------------------------------------

    def test_the_tools_and_groups_are_the_originals(self):
        self.assertEqual(self.strings(self.fn["tools"]), TOOLS)
        self.assertEqual(self.strings(self.fn["groups"]), list(GROUPS))
        self.assertEqual(sum(len(v) for v in GROUPS.values()), len(TOOLS))

    # --- which tools a session advertises -------------------------------

    def test_activation_agrees_with_the_original(self):
        names = list(GROUPS) + ["nosuch", "CORE", "", "all", "*", "fs-danger"]
        cases = [("", ""), ("", "core"), ("", "all"), ("", "*"),
                 ("", "core,monitor"), ("", " core , fs "), ("", "core,,fs"),
                 ("", "nosuch"), ("", "core,nosuch,fs"), ("", "CORE"),
                 ("ssh_exec", ""), ("ssh_exec,ssh_read_file", "all"),
                 (" ssh_exec , nosuch_tool ", "core"), (",,", "monitor"),
                 ("ssh_service", "core"), ("", "service,service"),
                 ("", "admin,xfer,batch,fs,fs-danger,monitor,core,service")]
        random.seed(4321)
        for _ in range(120):
            cases.append(("" if random.random() < 0.7 else
                          ",".join(random.sample(TOOLS, random.randint(1, 4))),
                          ",".join(random.sample(names, random.randint(1, 3)))))
        for indiv, groups in cases:
            want_tools, want_unknown, want_saving = Original.active(indiv, groups)
            got_tools, got_unknown, got_saving = self.activation(indiv, groups)
            self.assertEqual(got_tools, want_tools, (indiv, groups))
            self.assertEqual(got_unknown, want_unknown, (indiv, groups))
            self.assertEqual(got_saving, want_saving, (indiv, groups))

    def test_the_default_is_five_tools_and_the_banner_says_87(self):
        tools, unknown, saving = self.activation("", "")
        self.assertEqual(tools, GROUPS["core"])
        self.assertEqual(unknown, [])
        self.assertEqual(saving, 87)                 # the number the banner prints

    def test_an_individual_whitelist_beats_the_groups(self):
        tools, _u, _s = self.activation("ssh_delete_file", "core")
        self.assertEqual(tools, ["ssh_delete_file"])

    def test_a_name_nobody_has_matches_nothing(self):
        tools, _u, _s = self.activation("ssh_rm_rf_slash", "")
        self.assertEqual(tools, [])

    # --- the parse ------------------------------------------------------

    def test_the_parse_agrees_with_the_regex(self):
        """Strings built to break it: markers touching, empty values, runs
        of underscores, names that are digits, no markers at all.  The
        shipped run is 2 500 so the suite stays quick; the same test was
        run once at 10 000 with no disagreement."""
        random.seed(77)
        words = ["cpu", "mem", "disk", "load", "uptime", "a", "x1", "9", "_", "__",
                 "a_b", "CPU", "long_name_here"]
        chunks = ["", "\n", " ", "12.3", "3129/7823MB (40.0%)", "0.52 0.48 0.44",
                  "___", "____", "_", "up 3 weeks", "x", "  spaced  ", "\n\n"]
        cases = [HEALTH, "", "___", "______", "___cpu___", "___cpu______mem___",
                 "before___cpu___12___mem___34after", "___cpu___12___",
                 "no markers at all", "___9___1", "____cpu____12____",
                 "___a___\n___b___\n", "___cpu___12___cpu___34"]
        for _ in range(2_500):
            n = random.randint(0, 5)
            s = []
            for _ in range(n):
                if random.random() < 0.7:
                    s.append("___" + random.choice(words) + "___")
                s.append(random.choice(chunks))
            cases.append("".join(s))
        for out in cases:
            self.assertEqual(self.strings(self.call("secs", out)),
                             Original.sections(out), repr(out))
            self.assertEqual(self.parsed(out), Original.fields(out), repr(out))

    def test_the_real_output_parses_into_five_readings(self):
        self.assertEqual(self.parsed(HEALTH), Original.fields(HEALTH))
        self.assertEqual(sorted(self.parsed(HEALTH)),
                         ["cpu", "disk", "load", "mem", "uptime"])

    def test_an_empty_reading_swallows_the_marker_after_it(self):
        """A fragility this port inherits on purpose, and can now name.

        Drop one value and the two markers around the gap become a single
        marker carrying both names -- `_` is a word character and the
        regex is greedy, so `___cpu______mem___` is one marker called
        `cpu______mem`.  Both readings are gone; the three after them are
        untouched.  The original does exactly this, which is the point of
        checking rather than assuming.
        """
        broken = HEALTH.replace(NL + "12.3" + NL, "")
        got = self.parsed(broken)
        self.assertEqual(got, Original.fields(broken))
        self.assertNotIn("cpu", got)
        self.assertNotIn("mem", got)
        self.assertIn("cpu______mem", got)
        self.assertEqual(got["cpu______mem"], "3129/7823MB (40.0%)")
        self.assertIn("disk", got)
        # and the judgement does not pretend: two readings are missing, so
        # the machine is not called healthy, it is called unknown
        v = self.call("verdict", broken)
        self.assertEqual(self.get(v, "cpu"), -1)
        self.assertEqual(self.get(v, "worst"), 3)

    # --- reading a number out of a reading --------------------------------

    def test_each_shape_has_its_own_reader(self):
        """Four shapes come out of that one shell command, and the number at
        the front of `12G/40G (31%)` means nothing."""
        for text, want in (("12.3", 123), ("31%", 310), ("0.52", 5),
                           ("100.0", 1000), ("", -1), ("none", -1), ("7", 70)):
            self.assertEqual(self.call("tenths", text), want, text)
        for text, want in (("0.52 0.48 0.44", 52), ("9.10 8.0 7.0", 910),
                           ("18.2 16.0", 1820), ("3", 300), ("", -1)):
            self.assertEqual(self.call("hundredths", text), want, text)
        for text, want in (("12G/40G (31%)", 310), ("(5%)", 50),
                           ("84.5%", 845), ("no percent", -1), ("%", -1)):
            self.assertEqual(self.call("percent", text), want, text)

    def test_a_percentage_is_taken_from_the_two_integers(self):
        """Not from the percentage the string already carries: the shell
        printed `40.0` with one decimal, and 3129/7823 is 39.997."""
        self.assertEqual(self.call("ratio", "3129/7823MB (40.0%)"), 400)
        self.assertEqual(self.call("ratio", "1/2MB (50.0%)"), 500)
        self.assertEqual(self.call("ratio", "7823/7823MB (100%)"), 1000)
        self.assertEqual(self.call("ratio", "nothing"), -1)
        self.assertEqual(self.call("ratio", "5/0MB"), -1)

    # --- the judgement, which the original does not have -------------------

    def test_a_healthy_machine_is_quiet(self):
        v = self.call("verdict", HEALTH)
        self.assertEqual(self.get(v, "worst"), 0)
        self.assertEqual(self.get(v, "cpu"), 123)
        self.assertEqual(self.get(v, "mem"), 400)
        self.assertEqual(self.get(v, "disk"), 310)

    def test_each_threshold_bites(self):
        for field, value, level in ((("cpu", "88.0"), None, 1),
                                    (("cpu", "99.1"), None, 2),
                                    (("disk", "85%"), None, 1),
                                    (("disk", "95%"), None, 2),
                                    (("mem", "7000/7823MB"), None, 1),
                                    (("mem", "7700/7823MB"), None, 2),
                                    (("load", "9.10 8.0 7.0"), None, 1),
                                    (("load", "18.2 16.0 15.0"), None, 2)):
            name, text = field
            out = re.sub(rf"___{name}___\n[^\n]*", f"___{name}___\n{text}", HEALTH)
            self.assertEqual(self.get(self.call("verdict", out), "worst"), level,
                             (name, text))

    def test_a_reading_that_never_came_back_is_not_silently_fine(self):
        v = self.call("verdict", "")
        self.assertEqual(self.get(v, "worst"), 3)
        self.assertEqual(self.get(v, "cpu"), -1)

    # --- the fleet ---------------------------------------------------------

    def fleet(self, pairs):
        from core.runtime import Cons, NIL_VALUE
        out = NIL_VALUE
        for name, text in reversed(pairs):
            row = Cons(name, Cons(text, NIL_VALUE))
            out = Cons(row, out)
        return self.call("report", out)

    def test_a_fleet_comes_back_worst_first(self):
        hot = HEALTH.replace("\n12.3\n", "\n99.9\n")
        warm = HEALTH.replace("\n12G/40G (31%)\n", "\n36G/40G (85%)\n")
        r = self.fleet([("alpha", HEALTH), ("bravo", hot), ("charlie", warm),
                        ("delta", ""), ("echo", HEALTH)])
        rows = list_to_python(self.get(r, "rows"))
        names = ["".join(chr(c) for c in list_to_python(self.get(x, "name")))
                 if not isinstance(self.get(x, "name"), str) else self.get(x, "name")
                 for x in rows]
        worst = [self.get(x, "worst") for x in rows]
        self.assertEqual(worst, sorted(worst, reverse=True))
        self.assertEqual(names[0], "delta")           # nothing came back: 3
        self.assertEqual(self.get(r, "total"), 5)
        self.assertEqual(self.get(r, "alarm"), 1)
        self.assertEqual(self.get(r, "warn"), 1)
        self.assertEqual(self.get(r, "quiet"), 2)
        self.assertEqual(self.get(r, "mute"), 1)

    def test_two_hundred_machines_cost_what_a_call_can_afford(self):
        pairs = [(f"srv{i:03d}", HEALTH) for i in range(200)]
        self.fleet(pairs)
        self.assertLess(self.rt.steps, 2_500_000)   # 11 100 a machine


def _run_cli(argv):
    import contextlib, io as _io, sys as _sys
    out, err = _io.StringIO(), _io.StringIO()
    from core.cli import main
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class Terminal(unittest.TestCase):
    """`apps/fleet.lova`: the report, from a recorded sweep."""

    SWEEP = "apps/fleet/sweep.txt"

    def test_it_reports_the_fleet_worst_first(self):
        code, out, err = _run_cli(["run", "apps/fleet.lova", self.SWEEP,
                                   "--allow", "fs-read"])
        self.assertEqual(code, 0, err)
        self.assertIn("12 machines: 2 alarm, 3 warn, 6 ok, 1 silent", out)
        rows = [l for l in out.split(NL) if l.startswith(("ALARM", " warn", "   ok", "  ?"))]
        self.assertEqual(len(rows), 12)
        ranks = ["  ?", "ALARM", " warn", "   ok"]
        seen = [ranks.index(l[:5].replace("  ?  ", "  ?")[:5]
                            if l.startswith("  ?") else l[:5]) for l in rows]
        self.assertEqual(seen, sorted(seen))
        # the value is something a host can branch on: alarms * 100 + warns
        self.assertIn("=> 203", err)

    def test_it_cannot_read_a_file_it_was_not_granted(self):
        """The whole safety argument in one test: the policy declares
        `fs-read`, the host grants it, and without the grant the run does
        not happen -- not "is refused at the point of use", does not
        happen."""
        code, _out, err = _run_cli(["run", "apps/fleet.lova", self.SWEEP])
        self.assertNotEqual(code, 0)
        self.assertIn("fs-read", err)

    def test_the_policy_itself_can_reach_nothing(self):
        """`lib/fleet.lova` has no boundary in it at all, so no capability
        check can ever be against it: it is handed text and gives back a
        judgement.  This is what makes it testable on recordings."""
        source = io.open("lib/fleet.lova", encoding="utf-8").read()
        for effect in ("boundary", "fs-read", "fs-write", "net-send", "net-recv",
                       "clock", "stdin", "stdout"):
            self.assertNotIn("(" + effect, source, effect)


if __name__ == "__main__":
    unittest.main()
