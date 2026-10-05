from __future__ import annotations

"""Pagination helpers for graph-data sampling.

The hub sampler ranks all nodes by degree, takes ``hub_count`` seeds
starting at ``offset``, then pulls in their 1-hop neighbours (up to
``limit`` nodes total). ``offset`` therefore counts **hub seeds**, not
nodes — callers must advance by :func:`hub_page_size`, or better, follow
the ``next_offset`` cursor returned with each page.
"""


def hub_page_size(limit: int) -> int:
    return max(5, limit // 8)


def next_offset(offset: int, limit: int) -> int:
    return offset + hub_page_size(limit)
