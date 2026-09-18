"""fleet.py  --  the health-check half of the fleet policy, in Python.

A transliteration of `experiments/exp29/fleet.lova`, function for
function and name for name: RemoteX's `healthCheck` parse
(`stdout.split(/___(\\w+)___/).filter(Boolean)` and the pairing loop
after it), the four readers that pull a number out of a reading, the
thresholds, the fleet report, and `main`.

The same decomposition as the LOVA, deliberately: no regular
expressions (the LOVA walks the text by hand and so does this), no
classes, a record is a dict with the same field names, a list is a
list.  `iterate` becomes a `while` loop over the same state; `sort-by`
becomes `sort_by` below, which is the operator's own rule.
"""

from __future__ import annotations

import functools

NA = -1                                 # a reading that was not there


def sort_by(less, xs):
    """LOVA's `sort-by`: stable, and `a` before `b` only when
    `(less a b)` and not `(less b a)`, so a `le` comparator sorts as a
    `lt` one does."""
    def compare(a, b):
        ab = bool(less(a, b))
        ba = bool(less(b, a))
        return -1 if ab and not ba else (1 if ba and not ab else 0)
    return sorted(xs, key=functools.cmp_to_key(compare))


# --- the health parse -----------------------------------------------
#
# `stdout.split(/___(\w+)___/)`.  A word character is a letter, a digit
# or an underscore; the engine is greedy and backtracks, so the name a
# marker carries is the *longest* run of word characters with `___`
# after it.  With `_` itself a word character that is not a detail:
# `___cpu______mem___` is one marker named `cpu______mem`, not two.

def digit(c):
    return 48 <= c <= 57


def word_char(c):
    return ((97 <= c <= 122) or (65 <= c <= 90)) or ((48 <= c <= 57) or c == 95)


def three_bars(s, i):
    return (i + 3 <= len(s)
            and ord(s[i]) == 95 and ord(s[i + 1]) == 95 and ord(s[i + 2]) == 95)


# The end of the longest run of word characters from `i`.
def word_run(s, i):
    at = i
    while not (at >= len(s) or not word_char(ord(s[at]))):
        at = at + 1
    return at


# Greedy with backtracking, for this one pattern: from the longest run
# back toward the shortest, the first place with `___` after it wins.
# A name must not be empty, so the walk stops one past the opening.
def marker_end(s, i):
    stop = word_run(s, i + 3)
    at = stop
    while not (at <= i + 3 or three_bars(s, at)):
        at = at - 1
    return at


def marker_at(s, i):
    if not three_bars(s, i):
        return {"found": 0, "name": "", "after": i}
    e = marker_end(s, i)
    if e <= i + 3 or not three_bars(s, e):
        return {"found": 0, "name": "", "after": i}
    return {"found": 1, "name": s[i + 3:e], "after": e + 3}


# The next `___` at or after `i`, or the end of the text.  Jumping
# there rather than walking took one machine's health from 17 800
# steps to 11 100: a native search beats a loop written out.
def next_bars(s, i):
    if i >= len(s):
        return len(s)
    hit = s[i:len(s)].find("___")
    return len(s) if hit < 0 else i + hit


# The pieces the split gives, with the empty ones dropped: text, name,
# text, name, ... exactly as `.filter(Boolean)` leaves them.  The walk
# finds the markers; the text after the last one is added afterwards,
# because the walk stops at the end and has nowhere to put it.
def sections(s):
    w = {"at": next_bars(s, 0), "from": 0, "out": []}
    while not (w["at"] > len(s) - 1):
        m = marker_at(s, w["at"])
        if m["found"]:
            before = s[w["from"]:w["at"]]
            w = {"out": w["out"] + ([] if not before else [before]) + [m["name"]],
                 "at": m["after"], "from": m["after"]}
        else:
            w = {"out": w["out"], "at": next_bars(s, w["at"] + 1), "from": w["from"]}
    tail = s[w["from"]:len(s)]
    return w["out"] + ([] if not tail else [tail])


# Pairs, the original's `for (i = 0; i < sections.length - 1; i += 2)`:
# a name, then the text after it, trimmed.  An empty value shifts every
# pair after it, and this reproduces that rather than fixing it.
def fields(out):
    secs = sections(out) + []
    m = {}
    for i in range(0, len(secs) // 2 + 1):
        if 2 * i < len(secs) - 1:
            m[secs[2 * i]] = secs[2 * i + 1].strip()
    return m


# --- reading a number out of a reading ------------------------------
#
# Everything is integers: the readings arrive as text a shell printed,
# and a threshold on tenths of a per cent is a threshold on an
# integer.  The shell prints them in four shapes, so there are four
# readers, and getting it wrong is quiet -- `12G/40G (31%)` has a
# perfectly good number at the front that means nothing.

def first_digit(s):
    at = 0
    while not (at >= len(s) or digit(ord(s[at]))):
        at = at + 1
    return at


def end_of_digits(s, i):
    at = i
    while not (at >= len(s) or not digit(ord(s[at]))):
        at = at + 1
    return at


def digits_from(s, i):
    at, n = i, 0
    while not (at >= len(s) or not digit(ord(s[at]))):
        n = n * 10 + (ord(s[at]) - 48)
        at = at + 1
    return n


def first_number(s):
    i = first_digit(s)
    return NA if i >= len(s) else digits_from(s, i)


# The first number in `s`, scaled by ten to the `places`: "12.3" at one
# place is 123, "0.52" at two is 52, "31" at one is 310.  A missing
# decimal digit is a zero and an extra one is dropped, which is what
# reading to a fixed number of places means.
def decimals(s, places):
    i = first_digit(s)
    if i >= len(s):
        return NA
    whole = digits_from(s, i)
    j = end_of_digits(s, i)
    if j < len(s) and ord(s[j]) == 46:
        frac = s[j + 1:min(end_of_digits(s, j + 1), j + 1 + places)]
    else:
        frac = ""
    return whole * (10 ** places) + digits_from(frac, 0) * (10 ** (places - len(frac)))


# `12.3` -- what `top` gives, one place.
def tenths(s):
    return decimals(s, 1)


# `0.52 0.48 0.44` -- what `/proc/loadavg` gives, two places, and only
# the first of the three is a threshold anybody sets.
def hundredths(s):
    return decimals(s, 2)


# `12G/40G (31%)` -- what `df -h` gives.  The number that matters is
# the one against the `%`, not the one at the front: `12G` is how much
# is used and means nothing without the size.
def percent_tenths(s):
    m = s.find("%")
    if m < 0:
        return NA
    at = m
    while not (at <= 0 or not (digit(ord(s[at - 1])) or ord(s[at - 1]) == 46)):
        at = at - 1
    frm = at
    return NA if frm >= m else tenths(s[frm:m])


# `3129/7823MB (40.0%)` -- what `free -m` gives.  The ratio of the two
# integers rather than the percentage the string already carries.
#
# Rounded, not truncated: 3129/7823 is 39.997 per cent and the shell
# prints `40.0`, so truncating would disagree with the number this
# tool has always shown its operators.  Nothing is a float, so
# nothing drifts; it is the last digit that is a choice.
def ratio_tenths(s):
    bar = s.find("/")
    if bar < 0:
        return NA
    used = first_number(s[0:bar])
    whole = first_number(s[bar + 1:len(s)])
    if used == NA or whole == NA or whole <= 0:
        return NA
    return (2000 * used + whole) // (2 * whole)


# --- the judgement --------------------------------------------------
#
# Thresholds in tenths of a percent, in one place.  This is the part
# RemoteX does not have: it returns the five strings and the model
# decides, one server at a time.
#
#   0 ok      1 warn      2 alarm      3 nothing came back

CPU_WARN = 850
CPU_ALARM = 950
MEM_WARN = 850
MEM_ALARM = 950
DISK_WARN = 800
DISK_ALARM = 900
LOAD_WARN = 800                         # load average 8, in hundredths
LOAD_ALARM = 1600                       # and 16


def level_of(value, warn, alarm):
    if value == NA:
        return 3
    if value >= alarm:
        return 2
    if value >= warn:
        return 1
    return 0


def verdict(out):
    f = fields(out)
    cpu = tenths(f.get("cpu", ""))
    mem = ratio_tenths(f.get("mem", ""))
    disk = percent_tenths(f.get("disk", ""))
    load = hundredths(f.get("load", ""))
    levels = [level_of(cpu, CPU_WARN, CPU_ALARM),
              level_of(mem, MEM_WARN, MEM_ALARM),
              level_of(disk, DISK_WARN, DISK_ALARM),
              level_of(load, LOAD_WARN, LOAD_ALARM)]
    worst = 0
    for l in levels:
        worst = max(worst, l)
    return {"cpu": cpu, "mem": mem, "disk": disk, "load": load,
            "up": f.get("uptime", ""), "worst": worst, "levels": levels}


# --- the fleet ------------------------------------------------------
#
# A list of `(name output)` pairs in, one report out: the servers in
# trouble first, and the counts, so two hundred machines are a line and
# not two hundred blobs to read.

def report_of(pair):
    v = verdict(pair[1])
    return dict(v, name=pair[0])


def worse_first(a, b):
    if a["worst"] != b["worst"]:
        return a["worst"] > b["worst"]
    return a["name"] < b["name"]


def fleet_report(pairs):
    rs = sort_by(worse_first, [report_of(p) for p in pairs])
    return {"rows": rs,
            "total": len(rs),
            "alarm": len([r for r in rs if r["worst"] == 2]),
            "warn": len([r for r in rs if r["worst"] == 1]),
            "quiet": len([r for r in rs if r["worst"] == 0]),
            "mute": len([r for r in rs if r["worst"] == 3])}


# --- the sweep ------------------------------------------------------
#
# One text holding a whole sweep: a line that is just `---` ends a
# block, a block's first line is the machine's name, and the rest of
# the block is what its health check printed.  A machine that never
# answered has a name and nothing after it.

BAR = "---"


# The sweep's lines, cut into blocks at every `---` line.  A block is
# a list of lines; the cut line belongs to neither side.
def blocks_of(raw):
    w = {"done": [], "cur": []}
    for l in raw.split("\n"):
        if l.strip() == BAR:
            w = {"done": w["done"] + [w["cur"]], "cur": []}
        else:
            w = dict(w, cur=w["cur"] + [l])
    return w["done"] + [w["cur"]]


# A block as the `(name output)` pair `fleet-report` wants.
def pair_of(block):
    if not block:
        return ["", ""]
    return [block[0].strip(), "\n".join(block[1:])]


# A block with nothing in it at all is not a machine -- it is what two
# `---` lines in a row leave behind, or the end of the file.
def machines(raw):
    return [pair_of(b) for b in blocks_of(raw)
            if "\n".join(b).strip()]


# --- saying it ------------------------------------------------------

def row_line(r):
    return " ".join([r["name"], str(r["worst"])])


def counts_line(rep):
    return " ".join([str(rep["total"]), str(rep["alarm"]), str(rep["warn"]),
                     str(rep["quiet"]), str(rep["mute"])])


def main(sweep):
    rep = fleet_report(machines(sweep))
    return "\n".join([row_line(r) for r in rep["rows"]] + [counts_line(rep)])


def solve(sweep):
    return main(sweep)
