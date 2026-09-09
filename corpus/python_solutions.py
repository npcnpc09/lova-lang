"""Python reference solutions for LOVABench v2.

Two dicts:

  ``PYTHON_PURE``:   hand-rolled stdlib-only implementations.  Primitives
                     (p / tau / sigma / mu) are inlined per solution —
                     matches the style of Exp 07's PYTHON_SOLUTIONS dict
                     (each solution stands alone, no shared header).
  ``PYTHON_SYMPY``:  shortest idiomatic sympy solution per task with the
                     required ``from ... import`` line included.

Used by Exp 11 (LLM-token density measurement) and Exp 07+ (pass@1 /
error-class re-runs on v2).

Design note: solutions are "what a proficient Python user would write
from scratch," not "what Claude wrote in Exp 07" — for v2 we trade the
original benchmark artefact for comparability across 60 tasks.
Exp 07's v1 PYTHON_SOLUTIONS remains the historical record; merging
v1 + v2 happens at experiment load-time.
"""

from __future__ import annotations

from typing import Dict

# --- reusable primitive bodies (used only by PYTHON_PURE) ------------------

_P = """def p(n):
    if n<0: return 0
    if n==0: return 1
    t=[0]*(n+1); t[0]=1
    for m in range(1,n+1):
        k=1
        while True:
            g1=k*(3*k-1)//2; g2=k*(3*k+1)//2
            if g1>m: break
            s=-1 if k%2==0 else 1
            t[m]+=s*t[m-g1]
            if g2<=m: t[m]+=s*t[m-g2]
            k+=1
    return t[n]"""
_TAU = "def tau(n): return sum(1 for d in range(1,n+1) if n%d==0)"
_SIGMA = "def sigma(n): return sum(d for d in range(1,n+1) if n%d==0)"
_MU = """def mu(n):
    if n<=0: return 0
    if n==1: return 1
    m,pc,d=n,0,2
    while d*d<=m:
        if m%d==0:
            m//=d
            if m%d==0: return 0
            pc+=1
        else: d+=1
    if m>1: pc+=1
    return 1 if pc%2==0 else -1"""
_GCD = "from math import gcd"


def _pure(helpers, body: str) -> str:
    return "\n".join(list(helpers) + [body])


# --- PURE Python solutions for pb21-pb60 (v2 extensions) ------------------

PYTHON_PURE: Dict[str, str] = {
    # Deep composition (21-30)
    "pb21": _pure([_P, _TAU, _SIGMA],
                  "def solve(n): return p(tau(sigma(n)))"),
    "pb22": _pure([_P, _SIGMA, _GCD],
                  "def solve(a,b): return sigma(gcd(p(a),p(b)))"),
    "pb23": _pure([_TAU],
                  "def solve(n): return tau(tau(tau(n)))"),
    "pb24": _pure([_SIGMA, _TAU, _MU, _GCD],
                  "def solve(a,b): return mu(gcd(sigma(a),tau(b)))"),
    "pb25": _pure([_P, _TAU],
                  "def solve(n): return p(p(tau(n)))"),
    "pb26": _pure([_P, _TAU, _SIGMA, _GCD],
                  "def solve(a,b): return p(tau(a)) + sigma(gcd(a,b))"),
    "pb27": _pure([_P, _SIGMA, _TAU, _GCD],
                  "def solve(n):\n"
                  "    x=p(n)\n"
                  "    return gcd(sigma(x),tau(x))"),
    "pb28": _pure([_TAU, _SIGMA],
                  "def solve(a,b): return tau(sigma(a)+sigma(b))"),
    "pb29": _pure([_SIGMA, _P, _GCD],
                  "def solve(a,b): return sigma(p(gcd(a,b)))"),
    "pb30": _pure([_SIGMA, _TAU, _MU, _P],
                  "def solve(n): return sigma(tau(n)) + p(mu(n))"),

    # Conserve-heavy (31-40): Python uses assert to mirror conserve trap
    "pb31": _pure([_P],
                  "def solve(n,k):\n"
                  "    r=p(n); assert r==k; return r"),
    "pb32": _pure([_TAU],
                  "def solve(n,k):\n"
                  "    r=tau(n); assert r==k; return r"),
    "pb33": _pure([_GCD],
                  "def solve(a,b,k):\n"
                  "    r=gcd(a,b); assert r==k; return r"),
    "pb34": _pure([_P, _TAU],
                  "def solve(n,k):\n"
                  "    r=p(n)+tau(n); assert r==k; return r"),
    "pb35": _pure([_SIGMA, _GCD],
                  "def solve(a,b,k):\n"
                  "    r=sigma(gcd(a,b)); assert r==k; return r"),
    "pb36": _pure([_MU],
                  "def solve(n,k):\n"
                  "    r=mu(n); assert r==k; return r"),
    "pb37": _pure([_P, _TAU],
                  "def solve(n,k):\n"
                  "    r=p(tau(n)); assert r==k; return r"),
    "pb38": _pure([_TAU, _SIGMA],
                  "def solve(n,k):\n"
                  "    x=n; r=tau(x)+sigma(x); assert r==k; return r"),
    "pb39": _pure([_GCD],
                  "def solve(a,b,k):\n"
                  "    x=a; r=gcd(x,b); assert r==k; return r"),
    "pb40": _pure([_P, _TAU],
                  "def solve(n,k1,k2):\n"
                  "    r1=p(n); assert r1==k1\n"
                  "    r2=tau(n); assert r2==k2\n"
                  "    return r1+r2"),

    # Surprise-based (41-50)
    "pb41": _pure([_P],
                  "def solve(n,k): return abs(k-p(n))"),
    "pb42": _pure([_TAU],
                  "def solve(n,k): return abs(k-tau(n))"),
    "pb43": _pure([_P],
                  "def solve(n,m): return abs(p(n)-p(m))"),
    "pb44": _pure([_SIGMA],
                  "def solve(n): return abs(sigma(n)-2*n)"),
    "pb45": _pure([_P],
                  "def solve(n,k): return 1 if p(n)==k else 0"),
    "pb46": _pure([_GCD],
                  "def solve(a,b): return 1 if gcd(a,b)==1 else 0"),
    "pb47": _pure([_SIGMA],
                  "def solve(n,k): return 1 if sigma(n)==k else 0"),
    "pb48": _pure([_TAU, _SIGMA],
                  "def solve(n): return abs(tau(sigma(n))-sigma(tau(n)))"),
    "pb49": _pure([_MU],
                  "def solve(n): return 1 if mu(n)!=0 else 0"),
    "pb50": _pure([_P],
                  "def solve(a,b):\n"
                  "    x=a; y=b\n"
                  "    return abs(p(x)-p(y))"),

    # Let-heavy (51-60)
    "pb51": _pure([_P, _TAU],
                  "def solve(n):\n"
                  "    x=n; return p(x)+tau(x)"),
    "pb52": _pure([_P, _TAU, _GCD],
                  "def solve(a,b):\n"
                  "    x=gcd(a,b); return p(x)+tau(x)"),
    "pb53": _pure([_SIGMA, _TAU, _GCD],
                  "def solve(n):\n"
                  "    x=n; return gcd(sigma(x),tau(x))"),
    "pb54": _pure([_P, _TAU],
                  "def solve(n):\n"
                  "    x=p(n); return x+tau(x)"),
    "pb55": _pure([_TAU],
                  "def solve(n):\n"
                  "    x=n; y=tau(x); return x+y"),
    "pb56": _pure([_SIGMA, _TAU, _GCD],
                  "def solve(a,b):\n"
                  "    x=a; y=b; return gcd(sigma(x),tau(y))"),
    "pb57": _pure([_SIGMA],
                  "def solve(n):\n"
                  "    x=sigma(n); return x+x"),
    "pb58": _pure([_SIGMA, _GCD],
                  "def solve(a,b):\n"
                  "    x=sigma(a); y=sigma(b); return gcd(x,y)"),
    "pb59": _pure([_P, _SIGMA],
                  "def solve(n):\n"
                  "    x=n; return p(x)+sigma(x)"),
    "pb60": _pure([_P],
                  "def solve(a,b):\n"
                  "    x=a+b; return p(x)"),
}


# --- SYMPY-assisted solutions for pb21-pb60 -------------------------------

PYTHON_SYMPY: Dict[str, str] = {
    "pb21": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count, divisor_sigma\n"
            "def solve(n): return partition(divisor_count(divisor_sigma(n)))",
    "pb22": "from math import gcd\n"
            "from sympy import partition\n"
            "from sympy.ntheory import divisor_sigma\n"
            "def solve(a,b): return divisor_sigma(gcd(partition(a),partition(b)))",
    "pb23": "from sympy.ntheory import divisor_count\n"
            "def solve(n): return divisor_count(divisor_count(divisor_count(n)))",
    "pb24": "from math import gcd\n"
            "from sympy.ntheory import divisor_sigma, divisor_count, mobius\n"
            "def solve(a,b): return mobius(gcd(divisor_sigma(a),divisor_count(b)))",
    "pb25": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n): return partition(partition(divisor_count(n)))",
    "pb26": "from math import gcd\n"
            "from sympy import partition\n"
            "from sympy.ntheory import divisor_count, divisor_sigma\n"
            "def solve(a,b): return partition(divisor_count(a))+divisor_sigma(gcd(a,b))",
    "pb27": "from math import gcd\n"
            "from sympy import partition\n"
            "from sympy.ntheory import divisor_sigma, divisor_count\n"
            "def solve(n):\n"
            "    x=partition(n); return gcd(divisor_sigma(x),divisor_count(x))",
    "pb28": "from sympy.ntheory import divisor_count, divisor_sigma\n"
            "def solve(a,b): return divisor_count(divisor_sigma(a)+divisor_sigma(b))",
    "pb29": "from math import gcd\n"
            "from sympy import partition\n"
            "from sympy.ntheory import divisor_sigma\n"
            "def solve(a,b): return divisor_sigma(partition(gcd(a,b)))",
    "pb30": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count, divisor_sigma, mobius\n"
            "def solve(n): return divisor_sigma(divisor_count(n))+partition(mobius(n))",

    "pb31": "from sympy import partition\n"
            "def solve(n,k):\n"
            "    r=partition(n); assert r==k; return r",
    "pb32": "from sympy.ntheory import divisor_count\n"
            "def solve(n,k):\n"
            "    r=divisor_count(n); assert r==k; return r",
    "pb33": "from math import gcd\n"
            "def solve(a,b,k):\n"
            "    r=gcd(a,b); assert r==k; return r",
    "pb34": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n,k):\n"
            "    r=partition(n)+divisor_count(n); assert r==k; return r",
    "pb35": "from math import gcd\n"
            "from sympy.ntheory import divisor_sigma\n"
            "def solve(a,b,k):\n"
            "    r=divisor_sigma(gcd(a,b)); assert r==k; return r",
    "pb36": "from sympy.ntheory import mobius\n"
            "def solve(n,k):\n"
            "    r=mobius(n); assert r==k; return r",
    "pb37": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n,k):\n"
            "    r=partition(divisor_count(n)); assert r==k; return r",
    "pb38": "from sympy.ntheory import divisor_count, divisor_sigma\n"
            "def solve(n,k):\n"
            "    x=n; r=divisor_count(x)+divisor_sigma(x); assert r==k; return r",
    "pb39": "from math import gcd\n"
            "def solve(a,b,k):\n"
            "    x=a; r=gcd(x,b); assert r==k; return r",
    "pb40": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n,k1,k2):\n"
            "    r1=partition(n); assert r1==k1\n"
            "    r2=divisor_count(n); assert r2==k2\n"
            "    return r1+r2",

    "pb41": "from sympy import partition\n"
            "def solve(n,k): return abs(k-partition(n))",
    "pb42": "from sympy.ntheory import divisor_count\n"
            "def solve(n,k): return abs(k-divisor_count(n))",
    "pb43": "from sympy import partition\n"
            "def solve(n,m): return abs(partition(n)-partition(m))",
    "pb44": "from sympy.ntheory import divisor_sigma\n"
            "def solve(n): return abs(divisor_sigma(n)-2*n)",
    "pb45": "from sympy import partition\n"
            "def solve(n,k): return 1 if partition(n)==k else 0",
    "pb46": "from math import gcd\n"
            "def solve(a,b): return 1 if gcd(a,b)==1 else 0",
    "pb47": "from sympy.ntheory import divisor_sigma\n"
            "def solve(n,k): return 1 if divisor_sigma(n)==k else 0",
    "pb48": "from sympy.ntheory import divisor_count, divisor_sigma\n"
            "def solve(n): return abs(divisor_count(divisor_sigma(n))-divisor_sigma(divisor_count(n)))",
    "pb49": "from sympy.ntheory import mobius\n"
            "def solve(n): return 1 if mobius(n)!=0 else 0",
    "pb50": "from sympy import partition\n"
            "def solve(a,b):\n"
            "    x=a; y=b; return abs(partition(x)-partition(y))",

    "pb51": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n):\n"
            "    x=n; return partition(x)+divisor_count(x)",
    "pb52": "from math import gcd\n"
            "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(a,b):\n"
            "    x=gcd(a,b); return partition(x)+divisor_count(x)",
    "pb53": "from math import gcd\n"
            "from sympy.ntheory import divisor_sigma, divisor_count\n"
            "def solve(n):\n"
            "    x=n; return gcd(divisor_sigma(x),divisor_count(x))",
    "pb54": "from sympy import partition\n"
            "from sympy.ntheory import divisor_count\n"
            "def solve(n):\n"
            "    x=partition(n); return x+divisor_count(x)",
    "pb55": "from sympy.ntheory import divisor_count\n"
            "def solve(n):\n"
            "    x=n; y=divisor_count(x); return x+y",
    "pb56": "from math import gcd\n"
            "from sympy.ntheory import divisor_sigma, divisor_count\n"
            "def solve(a,b):\n"
            "    x=a; y=b; return gcd(divisor_sigma(x),divisor_count(y))",
    "pb57": "from sympy.ntheory import divisor_sigma\n"
            "def solve(n):\n"
            "    x=divisor_sigma(n); return x+x",
    "pb58": "from math import gcd\n"
            "from sympy.ntheory import divisor_sigma\n"
            "def solve(a,b):\n"
            "    x=divisor_sigma(a); y=divisor_sigma(b); return gcd(x,y)",
    "pb59": "from sympy import partition\n"
            "from sympy.ntheory import divisor_sigma\n"
            "def solve(n):\n"
            "    x=n; return partition(x)+divisor_sigma(x)",
    "pb60": "from sympy import partition\n"
            "def solve(a,b):\n"
            "    x=a+b; return partition(x)",
}
