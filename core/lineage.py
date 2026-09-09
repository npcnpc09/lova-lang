"""Lineage intrinsic — Axiom 5.

Every Node in LOVA carries session-unique provenance: ``uid``
(identifier), ``parent_uid`` (who it was derived from), ``root_uid``
(oldest ancestor), ``generation`` (depth from root), and a
``mutation_kind`` tag that describes HOW the derivation happened
(``root`` / ``clone`` / ``mutate-literal`` / ``mutate-operator``).

Design notes (aligned with axioms):

- **uid is metadata, not integer encoding.**  ``encode(node)`` bytes
  stay clean — lineage is a side-car table indexed by uid, Unison-style.
  Two structurally identical Nodes in the same session may share
  content-hash but have different uid (they are separate instances).
  This resolves tension between Axiom 1 (code is an integer) and
  Axiom 5 (lineage is intrinsic): the integer is the *content*; the
  lineage is the *instance history*.

- **Mutation has structure.**  MVP mutation strategy:
  - ``mutate-literal``: replace a LIT_INT with another literal in
    [-5, +5] of the current value.
  - ``mutate-operator``: within a same-arity, same-return-type
    equivalence class (e.g., ``{P, TAU, SIGMA, MOBIUS}``), swap the
    operator for a sibling.
  - ``clone``: exact copy (new uid, parent pointer, but identical bytes).

- **Paradigm lineage** (``../spec/paradigm-inheritance.md``):
  - Unison content-addressing: every definition has a stable identity.
  - Git commit DAGs: parent pointers + provenance.
  - DNA OS v3 Exp 55: Wright-Fisher coalescence at pool level.
  LOVA synthesises them: lineage is a first-class DAG queryable
  from within the language, not an external tool.
"""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.tokens import (
    LIT_INT, MERGE, GCD, MOBIUS, P, SIGMA, SIGNATURES, TAU, Node,
)


# --- records ----------------------------------------------------------------

@dataclass
class LineageRecord:
    """One ancestor-or-self entry in a LineageStore."""
    uid: int
    parent_uid: Optional[int]
    root_uid: int
    generation: int
    mutation_kind: str          # "root" / "clone" / "mutate-literal" / ...
    created_at: float           # Unix timestamp
    notes: str = ""

    def __repr__(self) -> str:
        p = f"<-{self.parent_uid}" if self.parent_uid is not None else ""
        return (f"[{self.uid}{p} gen={self.generation} "
                f"root={self.root_uid} {self.mutation_kind}]")


# --- the store --------------------------------------------------------------

class LineageStore:
    """Session-wide lineage database.

    Every Node that is *registered* receives a uid.  The store records
    the parent_uid / generation / mutation_kind.  Unregistered Nodes
    are fine (they are just authoring-time AST with no lineage), but
    once they enter the evolutionary lifecycle (mutation, variant
    competition, dispatch) they should be registered.
    """

    def __init__(self, seed: int = 0):
        self._next_uid = itertools.count(1)
        self._records: Dict[int, LineageRecord] = {}
        self._rng = random.Random(seed)

    # ---- registration ---------------------------------------------------

    def register_root(self, node: Node, notes: str = "") -> int:
        """Register a fresh root Node (no parent).  Returns assigned uid."""
        uid = next(self._next_uid)
        self._records[uid] = LineageRecord(
            uid=uid,
            parent_uid=None,
            root_uid=uid,
            generation=0,
            mutation_kind="root",
            created_at=time.time(),
            notes=notes,
        )
        node.uid = uid  # mutate the node's metadata
        return uid

    def _register_child(
        self,
        node: Node,
        parent_uid: int,
        mutation_kind: str,
        notes: str = "",
    ) -> int:
        uid = next(self._next_uid)
        parent = self._records[parent_uid]
        self._records[uid] = LineageRecord(
            uid=uid,
            parent_uid=parent_uid,
            root_uid=parent.root_uid,
            generation=parent.generation + 1,
            mutation_kind=mutation_kind,
            created_at=time.time(),
            notes=notes,
        )
        node.uid = uid
        return uid

    # ---- derivations ----------------------------------------------------

    def clone(self, parent: Node) -> Node:
        """Create a structurally identical copy with a fresh uid."""
        if parent.uid is None:
            raise ValueError("parent must be registered before clone()")
        child = _deep_copy_node(parent)
        self._register_child(child, parent.uid, "clone")
        return child

    def mutate(
        self,
        parent: Node,
        strength: float = 0.3,
        kind: str = "auto",
    ) -> Node:
        """Create a mutated variant with a fresh uid.

        ``strength`` is the per-Node probability of perturbing at each
        subtree location.  ``kind`` can be ``"literal"``,
        ``"operator"``, or ``"auto"`` (pick one at random per mutation
        opportunity).
        """
        if parent.uid is None:
            raise ValueError("parent must be registered before mutate()")
        child = _deep_copy_node(parent)
        mutations_applied: List[str] = []
        _mutate_inplace(child, self._rng, strength, kind, mutations_applied)
        applied = ",".join(mutations_applied) if mutations_applied else "no-op"
        self._register_child(
            child, parent.uid, "mutate", notes=f"strength={strength} [{applied}]"
        )
        return child

    # ---- queries --------------------------------------------------------

    def record(self, uid: int) -> LineageRecord:
        return self._records[uid]

    def ancestors(self, uid: int) -> List[LineageRecord]:
        """Ordered list self → parent → ... → root."""
        out = []
        cur: Optional[int] = uid
        while cur is not None:
            rec = self._records[cur]
            out.append(rec)
            cur = rec.parent_uid
        return out

    def is_ancestor_of(self, a: int, b: int) -> bool:
        """Is ``a`` an ancestor of ``b`` (or equal)?"""
        for rec in self.ancestors(b):
            if rec.uid == a:
                return True
        return False

    def roots(self) -> List[int]:
        """All registered root uids."""
        return [r.uid for r in self._records.values() if r.parent_uid is None]

    def descendants_of(self, uid: int) -> List[int]:
        """All registered descendants (not including self)."""
        out = []
        for rec in self._records.values():
            if rec.uid == uid:
                continue
            if self.is_ancestor_of(uid, rec.uid):
                out.append(rec.uid)
        return out

    def tree_str(self) -> str:
        """Render the full lineage DAG as an indented tree."""
        by_parent: Dict[Optional[int], List[int]] = {}
        for rec in self._records.values():
            by_parent.setdefault(rec.parent_uid, []).append(rec.uid)

        def _render(uid: int, depth: int) -> List[str]:
            rec = self._records[uid]
            line = ("  " * depth + f"{rec}")
            if rec.notes:
                line += f"  # {rec.notes}"
            out = [line]
            for child_uid in sorted(by_parent.get(uid, [])):
                out.extend(_render(child_uid, depth + 1))
            return out

        lines: List[str] = []
        for root in sorted(by_parent.get(None, [])):
            lines.extend(_render(root, 0))
        return "\n".join(lines)

    def coalescence_stats(self) -> Dict[str, int]:
        """Wright-Fisher style stats — how many roots, how many alive
        generations, how deep the deepest lineage is."""
        return {
            "n_roots": len(self.roots()),
            "n_records": len(self._records),
            "max_generation": max((r.generation for r in self._records.values()),
                                  default=0),
            "n_leaves": sum(
                1 for r in self._records.values()
                if not any(
                    other.parent_uid == r.uid for other in self._records.values()
                )
            ),
        }


# --- helpers ----------------------------------------------------------------

def _deep_copy_node(node: Node) -> Node:
    """Recursive copy of a Node tree; uid is cleared on the copy."""
    if node.op == LIT_INT:
        cp = Node(op=LIT_INT, args=[int(node.args[0])])
    else:
        new_args = [
            _deep_copy_node(c) if isinstance(c, Node) else c
            for c in node.args
        ]
        cp = Node(op=node.op, args=new_args)
    cp.uid = None
    return cp


# Mutation equivalence classes — operators that can be swapped for each
# other without changing the tree's type well-formedness.  Each group
# shares (arity, in_type-pattern, out_type).
_SWAP_GROUPS = [
    frozenset({P, TAU, SIGMA, MOBIUS}),   # arity 1, Int -> Int, nt
    frozenset({MERGE, GCD}),              # arity 2, Int x Int -> Int
]


def _swap_group_for(op: int) -> Optional[frozenset]:
    for g in _SWAP_GROUPS:
        if op in g:
            return g
    return None


def _mutate_inplace(
    node: Node,
    rng: random.Random,
    strength: float,
    kind: str,
    log: List[str],
) -> None:
    """Walk ``node`` in place, applying mutations with probability ``strength``."""
    if rng.random() < strength:
        effective_kind = kind
        if kind == "auto":
            effective_kind = rng.choice(["literal", "operator"])
        if effective_kind == "literal" and node.op == LIT_INT:
            old = int(node.args[0])
            # swap for a random nearby literal (non-zero delta)
            delta = rng.randint(-5, 5)
            while delta == 0:
                delta = rng.randint(-5, 5)
            new = old + delta
            node.args[0] = new
            log.append(f"lit:{old}->{new}")
        elif effective_kind == "operator":
            g = _swap_group_for(node.op)
            if g is not None and len(g) > 1:
                candidates = sorted(g - {node.op})
                new_op = rng.choice(candidates)
                old_name = SIGNATURES[node.op]["name"]
                new_name = SIGNATURES[new_op]["name"]
                node.op = new_op
                log.append(f"op:{old_name}->{new_name}")
    # Recurse into children (except for LIT_INT, whose args is a scalar)
    if node.op != LIT_INT:
        for child in node.args:
            if isinstance(child, Node):
                _mutate_inplace(child, rng, strength, kind, log)


# --- integration with the Node class ----------------------------------------
#
# We extend ``Node`` with an optional ``uid`` attribute without touching
# its existing ``__eq__`` / ``__repr__`` semantics (which live in
# ``core.tokens``).  At import time we monkey-patch __init__ to default
# uid to None; a more integrated solution lands in Milestone 5 when Node
# is revisited as a full class.

def _patch_node() -> None:
    original_init = Node.__init__

    def new_init(self, op: int, args: list, uid: Optional[int] = None) -> None:
        original_init(self, op, args)
        self.uid = uid

    Node.__init__ = new_init  # type: ignore[method-assign]


_patch_node()
