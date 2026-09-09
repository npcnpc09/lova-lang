"""LOVA core — reference implementation.

Module layout (most not yet implemented):

- ``tokens``       — the 64-token table + integer-sequence encoder/decoder
- ``types``        — position-directed type system
- ``runtime``      — token-sequence interpreter
- ``conservation`` — Δ-check + budget enforcement
- ``lineage``      — provenance tracking
- ``surface``      — Stage-1 s-expression ↔ token sequence pretty-printer

See ``../CLAUDE.md`` for project orientation and ``../spec/axioms.md``
for the ten design invariants.
"""
