"""Counts into a picture, without getting the bit order wrong.

A quantum circuit that encodes an image returns what every circuit returns: a
dictionary of bitstrings to counts. Turning that back into pixels is fifteen
lines of arithmetic, and the fifteen lines are the same every time, and the bit
order is wrong the first time for everybody. Qiskit reports the LEFTMOST
character as the HIGHEST-numbered qubit, so a naive read gives the image
mirrored and nobody notices until the picture is asymmetric.

    from qsim_sdk import images

    job = client.run(circuit, shots=300, engine="qpu.rigetti")
    pixels = images.from_counts(job["result"]["counts"], width=32)

`pixels[y][x]` is the probability that qubit `y * width + x` measured 1, which
under the standard encoding is that pixel's value. Nothing here is quantum: it
is post-processing of a result the service already certified, so it adds no
error and carries no claim of its own.

WHAT THIS IS FOR. One qubit per pixel, the value written as a rotation angle,
measured and read back. The technique is Huffman's (IBM Quantum, 2023): the
pixels are NOT entangled with each other, so location is carried by the qubit's
position in the circuit rather than by any quantum state, and an image larger
than the machine is simply split across several circuits. `stitch` puts those
back together.

WHERE THE CONSOLE STOPS AND THIS MODULE TAKES OVER. Submitting with
`params={"render": "image", "width": W}` makes the console draw the picture on
the job page and offer a PNG, which is the whole story for an image that fits
in ONE circuit: about 100 pixels on a 108-qubit device, so 10x10.

**A larger image is several jobs, and the console renders one job at a time.**
A 32x32 on Rigetti is eleven circuits, so the console shows eleven strips of
about three rows each and there is no way to join them there. Stitching across
jobs is this module's job:

    counts = [client.job(i)["result"]["counts"] for i in job_ids]
    pixels = images.stitch(counts, width=32)
    open("out.pgm", "wb").write(images.to_pgm(pixels))
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

__all__ = ["from_counts", "probabilities", "stitch", "to_pgm"]


def probabilities(counts: dict[str, int]) -> list[float]:
    """P(1) for each qubit, in qubit order: index 0 is qubit 0.

    THE BIT ORDER IS THE WHOLE POINT OF THIS FUNCTION. Qiskit writes the
    highest-numbered qubit first, so `"011"` means qubit 0 measured 1, qubit 1
    measured 1 and qubit 2 measured 0. Reading it left to right gives every
    image mirrored, which is invisible on a symmetric test pattern and obvious
    only once it matters.

    Spaces separate classical registers and are removed: a circuit measured
    into several registers reports `"01 10"`, and the pixels do not care where
    the register boundaries fell.
    """
    if not counts:
        return []
    total = sum(counts.values())
    if total <= 0:
        return []

    width = max(len(str(bits).replace(" ", "")) for bits in counts)
    ones = [0.0] * width
    for bits, n in counts.items():
        flat = str(bits).replace(" ", "")
        # Right-justified, so a short key from a device that trimmed leading
        # zeros still lines its qubits up with the long ones.
        flat = flat.rjust(width, "0")
        for index, char in enumerate(reversed(flat)):
            if char == "1":
                ones[index] += n
    return [count / total for count in ones]


def from_counts(
    counts: dict[str, int],
    *,
    width: int,
    height: int | None = None,
    invert: bool = False,
) -> list[list[float]]:
    """A 2D array of pixel values in [0, 1] from one circuit's counts.

    `height` defaults to whatever the qubit count divides into. A circuit
    carrying fewer qubits than `width * height` is padded with zeros rather
    than refused, because the last chunk of a split image is usually short.

    `invert` flips the sense, which is a presentation choice rather than a
    correction: whether 1 means ink or paper depends on how the angles were
    written, and both conventions appear in the literature.
    """
    if width <= 0:
        raise ValueError("width must be positive")

    values = probabilities(counts)
    if invert:
        values = [1.0 - v for v in values]

    rows = height if height is not None else -(-len(values) // width)
    out: list[list[float]] = []
    for y in range(rows):
        row = values[y * width:(y + 1) * width]
        row = row + [0.0] * (width - len(row))
        out.append(row)
    return out


def stitch(
    results: Iterable[dict[str, int]],
    *,
    width: int,
    height: int | None = None,
    invert: bool = False,
) -> list[list[float]]:
    """One image from several circuits, in submission order.

    An image wider than the machine is split across circuits, and because the
    pixels are not entangled that split costs nothing physically. It does mean
    the caller holds several results that have to go back together in the order
    they were sent, which is what this does.

        counts = [job["result"]["counts"] for job in jobs]
        pixels = images.stitch(counts, width=32)
    """
    flat: list[float] = []
    for counts in results:
        values = probabilities(counts)
        flat.extend([1.0 - v for v in values] if invert else values)

    rows = height if height is not None else -(-len(flat) // width)
    out: list[list[float]] = []
    for y in range(rows):
        row = flat[y * width:(y + 1) * width]
        row = row + [0.0] * (width - len(row))
        out.append(row)
    return out


def to_pgm(pixels: Sequence[Sequence[float]]) -> bytes:
    """The image as binary PGM, which every viewer and Pillow can open.

    PGM rather than PNG deliberately: it is a dozen lines of the standard
    library, and this package should not acquire an image dependency to hand
    back a greyscale array. Callers who already have Pillow or numpy will
    prefer to build from the array directly.
    """
    if not pixels or not pixels[0]:
        raise ValueError("no pixels to write")
    height, width = len(pixels), len(pixels[0])
    if any(len(row) != width for row in pixels):
        raise ValueError("every row must be the same width")

    hi = max((max(row) for row in pixels), default=0.0)
    scale = (255.0 / hi) if hi > 0 else 0.0
    body = bytearray()
    for row in pixels:
        for value in row:
            body.append(max(0, min(255, int(value * scale))))
    return b"P5\n%d %d\n255\n" % (width, height) + bytes(body)
