"""Elliptic curves over small prime fields, and the oracle Shor's DLP needs.

Nothing here is quantum. This module finds real curves, enumerates their points,
and builds the "add a fixed point R" permutation from the actual group law. The
permutation is built from PUBLIC data only: the curve, the generator P and the
public key Q. The secret d is never used to construct anything, only to check
the answer at the end.
"""
from __future__ import annotations

from dataclasses import dataclass

Point = tuple[int, int] | None      # None is the point at infinity


def _inv(a: int, p: int) -> int:
    return pow(a % p, p - 2, p)


def add(P1: Point, P2: Point, a: int, p: int) -> Point:
    """The elliptic curve group law on y^2 = x^3 + ax + b over F_p."""
    if P1 is None:
        return P2
    if P2 is None:
        return P1
    x1, y1 = P1
    x2, y2 = P2
    if x1 == x2 and (y1 + y2) % p == 0:
        return None
    if P1 == P2:
        lam = (3 * x1 * x1 + a) * _inv(2 * y1, p) % p
    else:
        lam = (y2 - y1) * _inv(x2 - x1, p) % p
    x3 = (lam * lam - x1 - x2) % p
    y3 = (lam * (x1 - x3) - y1) % p
    return (x3, y3)


def mul(k: int, P1: Point, a: int, p: int) -> Point:
    r: Point = None
    acc = P1
    while k:
        if k & 1:
            r = add(r, acc, a, p)
        acc = add(acc, acc, a, p)
        k >>= 1
    return r


def points(a: int, b: int, p: int) -> list[Point]:
    pts: list[Point] = [None]
    for x in range(p):
        rhs = (x * x * x + a * x + b) % p
        for y in range(p):
            if y * y % p == rhs:
                pts.append((x, y))
    return pts


def order_of(P1: Point, a: int, p: int) -> int:
    n, acc = 1, P1
    while acc is not None:
        acc = add(acc, P1, a, p)
        n += 1
    return n


@dataclass
class Curve:
    p: int
    a: int
    b: int
    order: int              # number of points, including infinity
    gen: Point              # a generator of the whole group
    pts: list[Point]        # public enumeration, index 0 is infinity

    @property
    def bits(self) -> int:
        return (self.order - 1).bit_length()

    def index(self, P1: Point) -> int:
        return self.pts.index(P1)


def find_cyclic_curve(target_order: int, p_max: int = 4096) -> Curve | None:
    """A curve whose group is CYCLIC of exactly `target_order` points.

    Powers of two are used as targets so the quantum Fourier transform over the
    counting registers is exact: the register dimension equals the group order,
    so the algorithm is deterministic and every error observed downstream comes
    from the device rather than from truncated arithmetic. A prime-order curve
    runs the identical circuit and needs a few extra shots of classical
    post-processing; the qubit count, which is what this experiment measures,
    is unchanged.
    """
    for p in range(5, p_max):
        if not _is_prime(p):
            continue
        # Hasse: |#E - (p+1)| <= 2*sqrt(p). Skip primes that cannot reach it.
        if abs(target_order - (p + 1)) > 2 * int(p ** 0.5) + 1:
            continue
        for a in range(p):
            for b in range(p):
                if (4 * a * a * a + 27 * b * b) % p == 0:
                    continue        # singular
                pts = points(a, b, p)
                if len(pts) != target_order:
                    continue
                for P1 in pts[1:]:
                    if order_of(P1, a, p) == target_order:
                        return Curve(p, a, b, target_order, P1, pts)
    return None


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for f in range(2, int(n ** 0.5) + 1):
        if n % f == 0:
            return False
    return True


def add_point_permutation(curve: Curve, R: Point, width: int) -> list[int]:
    """perm[i] = index of (pts[i] + R), as a permutation on 2^width basis states.

    Indices past the end of the group are fixed points: they are never populated,
    because the register starts at the identity and only ever moves inside the
    group. Built by real point addition, from R alone.
    """
    size = 1 << width
    perm = list(range(size))
    lookup = {pt: i for i, pt in enumerate(curve.pts)}
    for i, pt in enumerate(curve.pts):
        perm[i] = lookup[add(pt, R, curve.a, curve.p)]
    assert sorted(perm) == list(range(size)), "not a permutation"
    return perm
