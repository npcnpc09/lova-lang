"""The FPS kit, checked against the kit it was ported from.

`lib/fps.lova` is a port of the rules of KenneyNL/Starter-Kit-FPS
(MIT).  `Original` below is a transliteration of the kit's
`objects/player.gd`, `objects/enemy.gd` and `scripts/weapon.gd` with
its two weapon resources -- the wanted velocity built in the player's
own frame and turned by `transform.basis`, the lerp of a sixth,
gravity's gain of twenty a second and its cancellation on the floor
and the ceiling, two jumps of eight, the camera's dip of a tenth of a
metre eased at a fifth of a second, the blaster's three shots of
twenty-five every quarter second and the repeater's one of ten every
tenth, the spread, the knockback of the aim and of the body, health a
hundred, the enemies' hover and their five damage every quarter second
from five metres, and the world's bottom at minus ten -- in floating
point, with the same collision model the port uses in place of Godot's
physics: boxes under a segment with a radius, spheres for the enemies,
and a segment for every shot.  That model, and the generator the
random draws come from, are the two things here that are ours rather
than the kit's, and the header of `lib/fps.lova` says so.

What the oracle shares with the port, and therefore cannot catch:

* **The weapon table** -- damage, cooldown, spread, shot count,
  knockback and the two knockback ranges -- is written out below in the
  port's own units (the aim's kick in 16 384ths of a turn, the
  cooldown in ticks), read from the same two `.tres` files but not
  read again *from* the port.  A number mistyped in both places would
  pass.
* **The generator**: the same linear congruential recurrence, the same
  draw of the fifteen bits above the low sixteen, the same parity for
  the knockback's sign, and the same order of draws.  It is ours, not
  the kit's; the test can only say the two agree about it.
* **The sines**, which are `lib/fixed.lova`'s table of 256ths of a
  turn, **the integer unit vector a shot is cast along**, and **the
  bisection behind `atan2`**.  A hit is a discrete event -- a quarter
  of an enemy's health or nothing -- so a direction that differed in
  the fourth figure would make the two disagree about something
  neither got wrong.  The angles themselves are integers in both,
  because the port never does arithmetic finer than one 16 384th of a
  turn on them.

Everything else -- every rule, every order of operations, every
collision -- is written out here from the GDScript and compared.

`test_it_agrees_tick_by_tick` runs both from the same state for one
tick at a time over a scripted play of 642 ticks -- standing, stepping
sideways and diagonally, looking round, jumping twice, walking into an
enemy's fire, emptying the repeater and then the blaster into it until
it is destroyed, crossing the gap to the next island with a jump,
walking into a wall and sliding along it, and stepping clear and off
the edge of the world -- and compares the player, every enemy and every
impact to within a few thousandths.  `test_it_agrees_over_a_run` lets
the two run free over the same keys and checks that the same things
happened: the same enemies destroyed, the same damage taken, the same
number of falls.
"""

from __future__ import annotations

import math
import unittest

from core.cli import build
from core.runtime import Runtime, _call, _map_key, evaluate, list_to_python

F = 65536
A = 16384
DT = 1 / 60

API = """\
(use "fps")
(rec new new-game tick tick input input still still
     p (lambda w (get w p))
     enemies (lambda w (get w enemies))
     impacts (lambda w (get w impacts))
     solids (lambda w (get w solids))
     restarts (lambda w (get w restarts))
     rng (lambda w (get w rng)))
"""


# --- the port's arithmetic, where a discrete answer depends on it ---------------

SIN_Q = [0, 25, 50, 75, 100, 125, 150, 175, 200, 224, 249, 273, 297,
         321, 345, 369, 392, 415, 438, 460, 483, 505, 526, 548, 569, 590,
         610, 630, 650, 669, 688, 706, 724, 742, 759, 775, 792, 807, 822,
         837, 851, 865, 878, 891, 903, 915, 926, 936, 946, 955, 964, 972,
         980, 987, 993, 999, 1004, 1009, 1013, 1016, 1019, 1021, 1023, 1024, 1024]


def sin_t(ang):
    """`lib/fixed.lova`'s sine: 256ths of a turn in, 1024ths out."""
    k = ang % 256
    if k <= 64:
        return SIN_Q[k]
    if k <= 128:
        return SIN_Q[128 - k]
    if k <= 192:
        return -SIN_Q[k - 128]
    return -SIN_Q[256 - k]


def cos_t(ang):
    return sin_t(ang + 64)


def isqrt_l(n):
    """`lib/fixed.lova`'s integer square root: twelve rounds of Newton."""
    if n < 4:
        return 1 if n > 0 else 0
    x = max(1024, n // 1024)
    for _ in range(12):
        x = (x + n // x) // 2
    return x


def cam_dir(dx, dy, dz, yaw, pitch):
    """A direction in the camera's frame carried into the world, in 1024ths."""
    cp, sp = cos_t(pitch // 64), sin_t(pitch // 64)
    cy, sy = cos_t(yaw // 64), sin_t(yaw // 64)
    y1 = (dy * cp - dz * sp) // 1024
    z1 = (dy * sp + dz * cp) // 1024
    return ((dx * cy + z1 * sy) // 1024, y1, (z1 * cy - dx * sy) // 1024)


def unit_of(v):
    """The same direction at unit length, and the length it had."""
    n = max(1, isqrt_l(v[0] ** 2 + v[1] ** 2 + v[2] ** 2))
    return ((v[0] * 1024) // n, (v[1] * 1024) // n, (v[2] * 1024) // n, n)


def lcg(s):
    return (s * 1103515245 + 12345) % 2147483648


def rand(s, lo, hi):
    """The port's generator: the new state and a value in [lo, hi]."""
    s2 = lcg(s)
    return s2, lo + ((s2 // 65536) % 32768) * (hi - lo) // 32767


def rand_coin(s):
    """A draw's parity, which is what `randi() % 2` asks of it."""
    s2 = lcg(s)
    return s2, ((s2 // 65536) % 32768) % 2


def octant(n, d):
    """`lib/fixed.lova`'s bisection against the sine table."""
    lo = 0
    for step in (32, 16, 8, 4, 2, 1):
        mid = lo + step
        if n * cos_t(mid) >= d * sin_t(mid):
            lo = mid
    return lo


def atan2_t(y, x):
    """The angle of a direction, in 256ths: 0 along +x, 64 along +y."""
    if x == 0 and y == 0:
        return 0
    ax, ay = abs(x), abs(y)
    a = octant(ay, ax) if ay <= ax else 64 - octant(ax, ay)
    if x >= 0 and y >= 0:
        return a
    if x < 0 and y >= 0:
        return 128 - a
    if x < 0 and y < 0:
        return 128 + a
    return (256 - a) % 256


def fx(v):
    """A length in metres as the port holds it, in 65 536ths."""
    return round(v * F)


# --- the kit's rules, in floating point -----------------------------------------

BLASTER = dict(damage=25, cool=15, spread=1.0, shots=3, knock=40.0,
               kx=(65, 117), ky=(65, 104))
REPEATER = dict(damage=10, cool=6, spread=0.5, shots=1, knock=10.0,
                kx=(3, 7), ky=(3, 5))


class Original:
    """The kit's GDScript, transliterated, over the port's collision model."""

    SPEED = 5.0
    JUMP = 8.0
    JUMPS = 2
    GRAVITY = 21845 / F                  # 20 a second, as the port rounds it
    DIAG = 724 / 1024
    FEET, CAP, RADIUS = 3277 / F, 68813 / F, 19661 / F
    EDGE, STEP, SNAP = 13107 / F, 6554 / F, 1311 / F
    EYE, DIP = 1.0, -6554 / F
    BOTTOM = -10.0
    NEAR_XZ, NEAR_Y = 5.0, 4.0
    E_RADIUS, E_UP, AIM = 0.75, 0.25, 0.5
    E_RANGE, E_TIMER, E_DAMAGE = 5.0, 15, 5
    RANGE = 10.0
    HOVER = 217
    IMPACT_LIFE = 12
    WEAPONS = (BLASTER, REPEATER)

    def __init__(self, solids, enemies, start, rng):
        self.solids = solids
        self.start = start
        self.enemy_start = [dict(e) for e in enemies]
        self.rng = rng
        self.restarts = 0
        self.reset()

    def reset(self):
        self.x, self.y, self.z = self.start
        self.vx = self.vz = 0.0
        self.lx = self.lz = 0.0
        self.g = 0.0
        self.yaw = self.pitch = 0
        self.jumps = 0
        self.health = 100
        self.weapon = 0
        self.cool = 0
        self.dip = 0.0
        self.floored = self.ceiled = self.prev = False
        self.enemies = [dict(e) for e in self.enemy_start]
        self.impacts = []

    # --- the level ---

    def local(self, s, px, pz):
        a = s["yaw"] // 64
        c, sn = cos_t(a), sin_t(a)
        dx, dz = px - s["x"], pz - s["z"]
        return (dx * c - dz * sn) / 1024, (dx * sn + dz * c) / 1024

    def over(self, s, px, pz, margin):
        lx, lz = self.local(s, px, pz)
        return abs(lx) <= s["hx"] + margin and abs(lz - s["cz"]) <= s["hz"] + margin

    def near(self, s):
        return (abs(s["x"] - self.x) <= self.NEAR_XZ and abs(s["z"] - self.z) <= self.NEAR_XZ
                and abs(s["y"] - self.y) <= self.NEAR_Y)

    def eye_y(self):
        return self.y + self.EYE + self.dip

    # --- rays ---

    @staticmethod
    def ray_sphere(o, u, c, r, length):
        ux, uy, uz = u[0] / 1024, u[1] / 1024, u[2] / 1024
        mx, my, mz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
        proj = mx * ux + my * uy + mz * uz
        perp = mx * mx + my * my + mz * mz - proj * proj
        if perp > r * r:
            return None
        t = -proj - math.sqrt(max(0.0, r * r - perp))
        return None if t < 0 or t > length else t

    def ray_box(self, s, o, u, length):
        a = s["yaw"] // 64
        c, sn = cos_t(a), sin_t(a)
        ux = (u[0] * c - u[2] * sn) // 1024
        uz = (u[0] * sn + u[2] * c) // 1024
        lox, loz = self.local(s, o[0], o[2])
        loy = o[1] - s["y"]
        lo, hi, normal = 0.0, length, (0, 0, 0)
        for oo, d, qlo, qhi, ax in ((lox, ux, -s["hx"], s["hx"], 1),
                                    (loy, u[1], 0.0, s["top"], 2),
                                    (loz, uz, s["cz"] - s["hz"], s["cz"] + s["hz"], 3)):
            if d == 0:
                if oo < qlo or oo > qhi:
                    hi = -1.0
                continue
            t1, t2 = (qlo - oo) * 1024 / d, (qhi - oo) * 1024 / d
            first, last = min(t1, t2), max(t1, t2)
            if first > lo:
                lo = first
                sgn = -1024 if d > 0 else 1024
                normal = tuple(sgn if k + 1 == ax else 0 for k in range(3))
            if last < hi:
                hi = last
        if lo <= hi and lo <= length:
            return lo, normal
        return None, None

    def cast(self, o, u, length):
        """The nearest thing the ray meets: (t, kind, enemy, normal)."""
        best = (length, 0, None, (0, 0, 0))
        for e in self.enemies:
            if not e["alive"]:
                continue
            c = (e["x"], e["y"] + self.E_UP, e["z"])
            t = self.ray_sphere(o, u, c, self.E_RADIUS, best[0])
            if t is not None and t < best[0]:
                h = tuple(o[k] + u[k] * t / 1024 for k in range(3))
                n = tuple((h[k] - c[k]) * 1024 / self.E_RADIUS for k in range(3))
                best = (t, 1, e, n)
        for s in self.solids:
            t, n = self.ray_box(s, o, u, best[0])
            if t is not None and t < best[0]:
                a = s["yaw"] // 64
                c, sn = cos_t(a), sin_t(a)
                best = (t, 2, None,
                        ((n[0] * c + n[2] * sn) / 1024, n[1], (n[2] * c - n[0] * sn) / 1024))
        return best

    # --- shooting ---

    def one_shot(self):
        w = self.WEAPONS[self.weapon]
        sp = round(w["spread"] * F)
        self.rng, rx = rand(self.rng, -sp, sp)
        self.rng, ry = rand(self.rng, -sp, sp)
        u = unit_of(cam_dir(rx // 64, ry // 64, (-round(self.RANGE * F)) // 64,
                            self.yaw, self.pitch))
        length = u[3] * 64 / F
        o = (self.x, self.eye_y(), self.z)
        t, kind, enemy, n = self.cast(o, u, length)
        if not kind:
            return
        hit = tuple(o[k] + u[k] * t / 1024 + n[k] / 10240 for k in range(3))
        # the port conses the mark onto the front of the list
        self.impacts.insert(0, dict(x=hit[0], y=hit[1], z=hit[2], life=self.IMPACT_LIFE))
        if kind == 1:
            enemy["health"] -= w["damage"]
            if enemy["health"] <= 0:
                enemy["alive"] = 0

    def knock(self):
        w = self.WEAPONS[self.weapon]
        self.rng, sgn = rand_coin(self.rng)
        self.rng, kx = rand(self.rng, *w["kx"])
        self.rng, ky = rand(self.rng, *w["ky"])
        if not sgn:
            ky = -ky
        self.pitch = max(-A // 4, min(A // 4, self.pitch + kx))
        self.yaw = (self.yaw + ky) % A
        self.lz += w["knock"]

    # --- a tick ---

    def tick(self, mx, mz, jump, shoot, toggle, dyaw, dpitch):
        # handle_rotation, on the mouse path
        self.yaw = (self.yaw + dyaw) % A
        self.pitch = max(-A // 4, min(A // 4, self.pitch + dpitch))
        # handle_controls: the wanted velocity in the player's own frame
        both = mx and mz
        self.lx = mx * self.SPEED * (self.DIAG if both else 1.0)
        self.lz = mz * self.SPEED * (self.DIAG if both else 1.0)
        # action_shoot
        if shoot and not self.cool:
            # the tick it fires is the first of the period
            self.cool = self.WEAPONS[self.weapon]["cool"] - 1
            for _ in range(self.WEAPONS[self.weapon]["shots"]):
                self.one_shot()
            self.knock()
        else:
            self.cool = max(0, self.cool - 1)
        # action_jump, action_weapon_toggle
        if jump and self.jumps:
            self.g = -self.JUMP
            self.jumps -= 1
        if toggle:
            self.weapon = (self.weapon + 1) % 2
        # handle_gravity, on the floor and ceiling the last move left
        g = self.g + self.GRAVITY
        if g < 0 and self.ceiled:
            self.g = 0.0
        elif g > 0 and self.floored:
            self.g = 0.0
            self.jumps = self.JUMPS
        else:
            self.g = g
        self.move()
        # the camera's dip
        d = self.dip + (-self.dip) / 12
        landed = self.floored and self.g > 1 and not self.prev
        self.dip = self.DIP if landed else d
        self.prev = self.floored
        self.enemies_tick()
        for m in self.impacts:
            m["life"] -= 1
        self.impacts = [m for m in self.impacts if m["life"]]
        if self.y < self.BOTTOM or self.health < 0:
            self.reset()
            self.restarts += 1

    def move(self):
        c, sn = cos_t(self.yaw // 64), sin_t(self.yaw // 64)
        wx = (self.lx * c + self.lz * sn) / 1024
        wz = (self.lz * c - self.lx * sn) / 1024
        self.vx += (wx - self.vx) / 6
        self.vz += (wz - self.vz) / 6
        y0 = self.y
        near = [s for s in self.solids if self.near(s)]
        self.x += self.vx / 60
        self.z += self.vz / 60
        self.floored = self.ceiled = False
        for s in near:
            self.push_out(s)
        self.y -= self.g / 60
        for s in near:
            self.land(s, y0)
            self.bump(s, y0)

    def push_out(self, s):
        if not (s["y"] + s["top"] > self.y + self.FEET + self.STEP
                and s["y"] < self.y + self.CAP):
            return
        lx, lz = self.local(s, self.x, self.z)
        lz -= s["cz"]
        rx, rz = s["hx"] + self.RADIUS, s["hz"] + self.RADIUS
        if abs(lx) >= rx or abs(lz) >= rz:
            return
        ox, oz = rx - abs(lx), rz - abs(lz)
        flat = ox <= oz
        deep = ox if flat else oz
        lnx = (1024 if lx >= 0 else -1024) if flat else 0
        lnz = 0 if flat else (1024 if lz >= 0 else -1024)
        a = s["yaw"] // 64
        c, sn = cos_t(a), sin_t(a)
        nx = (lnx * c + lnz * sn) / 1024
        nz = (lnz * c - lnx * sn) / 1024
        # move_and_slide: out along the face's normal, and the velocity
        # keeps only what runs along the face
        into = (self.vx * nx + self.vz * nz) / 1024
        self.x += nx * deep / 1024
        self.z += nz * deep / 1024
        self.vx -= nx * into / 1024
        self.vz -= nz * into / 1024

    def land(self, s, y0):
        top = s["y"] + s["top"]
        if (self.g >= 0 and self.over(s, self.x, self.z, self.EDGE)
                and y0 + self.FEET >= top - self.SNAP and self.y + self.FEET <= top):
            self.y = top - self.FEET
            self.floored = True

    def bump(self, s, y0):
        if (self.g < 0 and self.over(s, self.x, self.z, self.RADIUS)
                and y0 + self.CAP <= s["y"] and self.y + self.CAP > s["y"]):
            self.y = s["y"] - self.CAP
            self.ceiled = True

    # --- the enemies ---

    def enemies_tick(self):
        for e in self.enemies:
            if not e["alive"]:
                continue
            e["ty"] += (cos_t((self.HOVER * e["time"]) // 64) / 1024) / 60
            e["y"] = e["ty"]
            # look_at the player: the yaw of it is what the picture turns
            # the model by
            e["yaw"] = atan2_t(fx(self.x) - fx(e["x"]), fx(self.z) - fx(e["z"])) * 64
            e["time"] += 1
            f = e["fire"] - 1
            if f > 0:
                e["fire"] = f
                continue
            e["fire"] = self.E_TIMER
            if self.sees(e):
                self.health -= self.E_DAMAGE

    def sees(self, e):
        o = (e["x"], e["y"] + self.E_UP, e["z"])
        aim = (self.x, self.y + self.AIM, self.z)
        d = unit_of(tuple((fx(aim[k]) - fx(o[k])) // 64 for k in range(3)))
        t = self.ray_sphere(o, d, aim, self.RADIUS, self.E_RANGE)
        if t is None:
            return False
        for s in self.solids:
            u, _n = self.ray_box(s, o, d, t)
            if u is not None and u < t:
                return False
        return True


# --- the port --------------------------------------------------------------------

class Port(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tree, _report = build(API)
        cls.rt = Runtime(max_steps=200_000_000, max_call_depth=10_000)
        api = evaluate(tree, cls.rt)
        cls.fn = {n: api.entries[_map_key(n, "rec")][1]
                  for n in ("new", "tick", "input", "still", "p", "enemies", "impacts",
                            "solids", "restarts", "rng")}

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

    # --- reading the world ---

    PLAYER = ("x", "y", "z", "vx", "vz", "g", "yaw", "pitch", "jumps", "health",
              "weapon", "cool", "dip", "floored", "ceiled", "prev")

    def player_of(self, world):
        p = self.get(world, "p")
        return {n: self.get(p, n) for n in self.PLAYER}

    def enemies_of(self, world):
        return [{n: self.get(e, n) for n in
                 ("i", "x", "y", "z", "ty", "yaw", "time", "health", "alive", "fire")}
                for e in list_to_python(self.call("enemies", world))]

    def impacts_of(self, world):
        return [{n: self.get(m, n) for n in ("x", "y", "z", "life")}
                for m in list_to_python(self.call("impacts", world))]

    def solids_of(self, world):
        """The level as the original wants it: metres, with the turn left in A."""
        out = []
        for s in list_to_python(self.call("solids", world)):
            out.append({n: self.get(s, n) / F for n in ("x", "y", "z", "hx", "hz", "cz", "top")})
            out[-1]["yaw"] = self.get(s, "yaw")
        return out

    def reference(self, world):
        p = self.player_of(world)
        ref = Original(self.solids_of(world),
                       [dict(x=e["x"] / F, y=e["y"] / F, z=e["z"] / F, ty=e["ty"] / F,
                             yaw=e["yaw"], time=e["time"], health=e["health"],
                             alive=e["alive"], fire=e["fire"])
                        for e in self.enemies_of(world)],
                       (p["x"] / F, p["y"] / F, p["z"] / F),
                       self.call("rng", world))
        return ref

    def sync(self, ref, world):
        """The reference takes the port's state, exactly."""
        p = self.player_of(world)
        ref.x, ref.y, ref.z = p["x"] / F, p["y"] / F, p["z"] / F
        ref.vx, ref.vz = p["vx"] / F, p["vz"] / F
        ref.g, ref.dip = p["g"] / F, p["dip"] / F
        ref.yaw, ref.pitch = p["yaw"], p["pitch"]
        ref.jumps, ref.health = p["jumps"], p["health"]
        ref.weapon, ref.cool = p["weapon"], p["cool"]
        ref.floored, ref.ceiled = bool(p["floored"]), bool(p["ceiled"])
        ref.prev = bool(p["prev"])
        ref.rng = self.call("rng", world)
        ref.enemies = [dict(x=e["x"] / F, y=e["y"] / F, z=e["z"] / F, ty=e["ty"] / F,
                            yaw=e["yaw"], time=e["time"], health=e["health"],
                            alive=e["alive"], fire=e["fire"])
                       for e in self.enemies_of(world)]
        ref.impacts = [dict(x=m["x"] / F, y=m["y"] / F, z=m["z"] / F, life=m["life"])
                       for m in self.impacts_of(world)]

    # --- the play ---

    @staticmethod
    def script():
        """(ticks, (mx, mz, jump, shoot, toggle, dyaw, dpitch)) across a game."""
        still = (0, 0, 0, 0, 0, 0, 0)
        ahead = (0, -1, 0, 0, 0, 0, 0)            # W: straight along the player's front
        shoot = (0, 0, 0, 1, 0, 0, 0)
        return [(40, still),                       # fall onto the big platform
                (1, (0, 0, 0, 0, 0, 1377, 0)),     # turn onto the first enemy
                (10, (1, 0, 0, 0, 0, 0, 0)),       # a step sideways
                (10, (-1, -1, 0, 0, 0, 0, 0)),     # and a diagonal back
                (1, (0, 0, 0, 0, 0, -200, 150)),   # look about
                (10, still),
                (1, (0, 0, 0, 0, 0, 200, -150)),
                (10, still),
                (1, (0, 0, 1, 0, 0, 0, 0)),        # a jump
                (20, still),
                (1, (0, 0, 1, 0, 0, 0, 0)),        # and the second, at the top
                (50, still),                       # down again
                (30, ahead),                       # walk at it, into its fire
                (12, (0, 1, 0, 0, 0, 0, 0)),       # S, back from the edge
                (10, still),
                (1, (0, 0, 0, 0, 1, 140, 870)),    # aim up at it, swap to the repeater
                (42, shoot),                       # seven shots of ten
                (1, (0, 0, 0, 0, 1, 0, 0)),        # back to the blaster
                (1, (0, 0, 0, 1, 0, 0, -60)),      # three pulls of three, the aim's
                (14, shoot),                       # kick corrected between them
                (1, (0, 0, 0, 1, 0, 0, -60)),
                (14, shoot),
                (1, (0, 0, 0, 1, 0, 0, -60)),
                (14, shoot),
                (10, still),
                (1, (0, 0, 0, 0, 0, 0, -850)),     # level the aim again
                (1, (0, 0, 0, 0, 0, -51, 0)),      # square onto the gap again
                (40, ahead),                       # walk at the edge
                (1, (0, -1, 1, 0, 0, 0, 0)),       # jump the gap to the next island
                (40, ahead),                       # and land on it
                (1, (0, -1, 0, 0, 0, -2469, 0)),   # {WALL} turn onto the low wall
                (32, ahead),                       # walk into it: the velocity
                (20, (0, 1, 0, 0, 0, 0, 0)),       # slides along it.  Then step clear
                (200, ahead)]                      # and walk off the island

    def keys(self):
        for ticks, held in self.script():
            for _ in range(ticks):
                yield held

    # --- one tick at a time ---

    def test_it_agrees_tick_by_tick(self):
        """From the same state, one tick of each lands within a few
        thousandths: the port's rounding to 65 536ths is the only
        difference there is."""
        world = self.fn["new"]
        ref = self.reference(world)
        ticks = 0
        tol = 0.004
        for held in self.keys():
            self.sync(ref, world)
            ref.tick(*held)
            world = self.call("tick", world, self.call("input", *held))
            ticks += 1
            p = self.player_of(world)
            for name, got, want in (("x", p["x"] / F, ref.x), ("y", p["y"] / F, ref.y),
                                    ("z", p["z"] / F, ref.z), ("vx", p["vx"] / F, ref.vx),
                                    ("vz", p["vz"] / F, ref.vz), ("g", p["g"] / F, ref.g),
                                    ("dip", p["dip"] / F, ref.dip)):
                self.assertAlmostEqual(got, want, delta=tol, msg=f"tick {ticks}: {name}")
            for name in ("yaw", "pitch", "jumps", "health", "weapon", "cool"):
                self.assertEqual(p[name], getattr(ref, name), f"tick {ticks}: {name}")
            for name in ("floored", "ceiled", "prev"):
                self.assertEqual(bool(p[name]), getattr(ref, name), f"tick {ticks}: {name}")
            got, want = self.enemies_of(world), ref.enemies
            self.assertEqual(len(got), len(want), f"tick {ticks}: enemies")
            for e, re_ in zip(got, want):
                self.assertEqual(e["health"], re_["health"], f"tick {ticks}: enemy health")
                self.assertEqual(bool(e["alive"]), bool(re_["alive"]), f"tick {ticks}: alive")
                self.assertEqual(e["fire"], re_["fire"], f"tick {ticks}: fire")
                self.assertEqual(e["yaw"], re_["yaw"], f"tick {ticks}: enemy yaw")
                for n in ("x", "y", "z"):
                    self.assertAlmostEqual(e[n] / F, re_[n], delta=tol,
                                           msg=f"tick {ticks}: enemy {n}")
            got, want = self.impacts_of(world), ref.impacts
            self.assertEqual(len(got), len(want), f"tick {ticks}: impacts")
            for m, rm in zip(got, want):
                self.assertEqual(m["life"], rm["life"], f"tick {ticks}: impact life")
                for n in ("x", "y", "z"):
                    self.assertAlmostEqual(m[n] / F, rm[n], delta=0.02,
                                           msg=f"tick {ticks}: impact {n}")
        self.assertEqual(ticks, 642)

    # --- a whole run ---

    def test_it_agrees_over_a_run(self):
        """Left to run free over the same keys, the same things happen."""
        world = self.fn["new"]
        ref = self.reference(world)
        for held in self.keys():
            ref.tick(*held)
            world = self.call("tick", world, self.call("input", *held))
        enemies = self.enemies_of(world)
        self.assertEqual([e["health"] for e in enemies],
                         [e["health"] for e in ref.enemies])
        self.assertEqual([bool(e["alive"]) for e in enemies],
                         [bool(e["alive"]) for e in ref.enemies])
        self.assertEqual(self.get(world, "restarts"), ref.restarts)
        p = self.player_of(world)
        self.assertEqual(p["health"], ref.health)
        self.assertAlmostEqual(p["x"] / F, ref.x, delta=0.1)
        self.assertAlmostEqual(p["z"] / F, ref.z, delta=0.1)

    # --- the play itself did something ---

    def test_the_play_exercises_the_rules(self):
        """The script is worth running: it destroys an enemy, takes fire,
        jumps twice and falls off the world."""
        world = self.fn["new"]
        jumps = destroyed = hurt = walled = 0
        health = 100
        # The wall segment of the script: the turn onto the low wall and
        # the walk into it.  The slide is looked for only there, and as
        # its own signature -- the velocity turning by more than thirty
        # degrees in one tick while the keys do not change.  A lerp
        # after a turn of the keys moves the velocity a few degrees a
        # tick; only a wall turns it in one.
        wall_turn = (0, -1, 0, 0, 0, -2469, 0)
        script = self.script()
        starts = [sum(t for t, _ in script[:i]) for i in range(len(script))]
        wall_at = [i for i, (_, held) in enumerate(script) if held == wall_turn]
        self.assertEqual(len(wall_at), 1, "the script has one turn onto the wall")
        window = range(starts[wall_at[0]], starts[wall_at[0]] + script[wall_at[0]][0]
                       + script[wall_at[0] + 1][0])
        previous = None
        tick_no = -1
        for held in self.keys():
            tick_no += 1
            before = self.player_of(world)
            restarts = self.get(world, "restarts")
            world = self.call("tick", world, self.call("input", *held))
            after = self.player_of(world)
            if held[2] and after["g"] < before["g"]:
                jumps += 1
            if after["health"] < health:
                hurt += 1
            health = after["health"]
            destroyed = max(destroyed,
                            sum(1 for e in self.enemies_of(world) if not e["alive"]))
            # a wall takes the velocity that ran into it (the review of
            # 2026-09-19 found a bare speed-drop count satisfied by tick
            # 51, a turn of the keys with no wall near, and by a fall
            # off the world; this looks for the slide itself)
            was = math.hypot(before["vx"] / F, before["vz"] / F)
            now = math.hypot(after["vx"] / F, after["vz"] / F)
            if (tick_no in window and held == previous and not held[3]
                    and self.get(world, "restarts") == restarts
                    and was > 1.0 and now > 1.0):
                turned = abs(math.atan2(after["vz"], after["vx"])
                             - math.atan2(before["vz"], before["vx"]))
                turned = min(turned, 2 * math.pi - turned)
                if turned > math.radians(30):
                    walled += 1
            previous = held
        self.assertGreaterEqual(jumps, 2)
        self.assertGreaterEqual(destroyed, 1)
        self.assertGreaterEqual(hurt, 1)
        self.assertGreaterEqual(walled, 1)
        self.assertGreaterEqual(self.get(world, "restarts"), 1)


class Examples(unittest.TestCase):
    """The rules carry their own examples; `lova check` runs them, and so
    does this, through the same command line a host would use."""

    def test_the_rules_carry_their_examples(self):
        import contextlib
        import io

        from core.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["check", "tools/bench/fps.lova", "n=1"])
        text = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("19/19 examples pass", text)


if __name__ == "__main__":
    unittest.main()
