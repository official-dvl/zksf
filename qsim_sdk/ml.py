"""Quantum programs as differentiable PyTorch layers.

This is the piece that turns a single submission into a workload. A photonic
generative model, a variational classifier or a quantum kernel is not one run:
it is a parameterised program evaluated thousands of times while an optimiser
walks its parameters, and the machine time those loops consume is what fills a
provider's queue.

    layer = PhotonicLayer(client, circuit, [1, 0, 1])
    opt   = torch.optim.Adam(layer.parameters(), lr=0.05)
    for step in range(200):
        loss = criterion(layer(), target)
        opt.zero_grad(); loss.backward(); opt.step()

Each forward is one job. Each backward is one job carrying 2P points, because
the whole gradient goes to /jobs/batch as a single parameterised sweep rather
than as 2P separate submissions.

**Gradients are central differences, not the parameter-shift rule.** The shift
rule is exact only where an output is a sinusoid of the parameter, which holds
for a Pauli rotation in a gate circuit and does not hold for a beamsplitter
angle in a linear-optical mesh or for a pulse amplitude in an analog sequence.
Central differences cost the same two evaluations per parameter and are correct
for both, at the price of a step-size choice: `eps` defaults to 0.01 rad and is
worth raising when the shot noise at your shot count swamps the difference.

Shot noise is the other thing to keep in view. A gradient estimated from N
shots carries an error of order 1/sqrt(N), so an optimiser that stalls at low
shot counts is usually reading noise rather than a flat landscape.

torch is not a dependency of qsim-sdk; install it yourself to use this module.
"""
from __future__ import annotations

from typing import Any, Sequence

__all__ = ["PhotonicLayer", "SequenceLayer"]


def _torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "qsim_sdk.ml needs PyTorch, which qsim-sdk does not install for you. "
            "pip install torch"
        ) from exc
    return torch


class _ProgramLayer:
    """Shared machinery for a parameterised program used as a torch Module.

    Subclasses say three things: how to name the program's free parameters, how
    to submit a list of parameter vectors, and how to turn one point's result
    into a probability mapping.
    """

    #: Filled in by __init__ once torch is known to be importable.
    param_names: list[str]

    def _submit(self, vectors: Sequence[Sequence[float]]) -> list[dict[str, float]]:
        raise NotImplementedError

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _distribution(item: dict[str, Any]) -> dict[str, float]:
        """Normalised probabilities for one point, or {} if it failed.

        A failed point is a zero vector rather than an exception: the sweep
        endpoint reports failures per point precisely so an optimiser can treat
        one as a bad point and carry on, and raising here would throw away the
        other 2P-1 evaluations that did succeed.
        """
        result = item.get("result") or {}
        counts = result.get("counts") or {}
        total = sum(counts.values())
        if not total:
            return {}
        return {k: v / total for k, v in counts.items()}

    def _vectors_to_probs(self, vectors: Sequence[Sequence[float]]):
        torch = _torch()
        job = self._submit(vectors)
        rows = []
        for item in job:
            dist = self._distribution(item)
            rows.append([dist.get(o, 0.0) for o in self.outcomes])
        return torch.tensor(rows, dtype=torch.float32)


def _make_function():
    """Build the autograd Function lazily, so importing this module without
    torch installed raises a clear ImportError rather than a NameError."""
    torch = _torch()

    class _Evaluate(torch.autograd.Function):
        @staticmethod
        def forward(ctx, theta, layer):
            ctx.layer = layer
            ctx.save_for_backward(theta)
            return layer._vectors_to_probs([theta.detach().tolist()])[0]

        @staticmethod
        def backward(ctx, grad_out):
            (theta,) = ctx.saved_tensors
            layer = ctx.layer
            eps = layer.eps
            base = theta.detach()

            # Every displaced point of the whole gradient in one job: 2P
            # evaluations, one round trip, one queue entry.
            vectors: list[list[float]] = []
            for i in range(base.numel()):
                for sign in (+1.0, -1.0):
                    shifted = base.clone()
                    shifted[i] = shifted[i] + sign * eps
                    vectors.append(shifted.tolist())

            probs = layer._vectors_to_probs(vectors)
            grads = []
            for i in range(base.numel()):
                derivative = (probs[2 * i] - probs[2 * i + 1]) / (2.0 * eps)
                grads.append(torch.dot(grad_out, derivative))
            return torch.stack(grads), None

    return _Evaluate


class PhotonicLayer:
    """A parameterised Perceval circuit as a torch Module.

    The layer's output is the probability of each detected Fock state, in a
    fixed order, which is the vector a classical network downstream consumes.
    The outcome list is fixed at construction rather than read from each run:
    which states appear varies with shot noise, and a layer whose output
    dimension changed between steps could not be trained.
    """

    def __new__(cls, *args: Any, **kwargs: Any):
        torch = _torch()

        class _Module(torch.nn.Module, _ProgramLayer):
            def __init__(
                self,
                client: Any,
                circuit: Any,
                input_state: Any,
                *,
                shots: int = 1000,
                engine: str = "photonic.slos.cpu",
                outcomes: Sequence[str] | None = None,
                init: Sequence[float] | None = None,
                eps: float = 0.01,
                timeout: float = 600.0,
            ) -> None:
                super().__init__()
                self.client = client
                self.circuit = circuit
                self.input_state = input_state
                self.shots = shots
                self.engine = engine
                self.eps = float(eps)
                self.timeout = timeout
                self.param_names = [p.name for p in circuit.get_parameters()]
                if not self.param_names:
                    raise ValueError(
                        "the circuit has no free parameters, so there is nothing to "
                        "train. Declare them with perceval.P('name')."
                    )
                start = list(init) if init is not None else [0.5] * len(self.param_names)
                if len(start) != len(self.param_names):
                    raise ValueError(
                        f"init has {len(start)} values for {len(self.param_names)} "
                        f"parameters {self.param_names}"
                    )
                self.theta = torch.nn.Parameter(torch.tensor(start, dtype=torch.float32))
                self.outcomes = list(outcomes) if outcomes else self._probe()
                self._fn = _make_function()

            def _probe(self) -> list[str]:
                """One run at the initial parameters, to learn which Fock states
                this circuit and input can produce."""
                job = self._submit([self.theta.detach().tolist()])
                return sorted(self._distribution(job[0]))

            def _submit(self, vectors):
                bindings = [dict(zip(self.param_names, v)) for v in vectors]
                job = self.client.run_parametric_sweep(
                    self.circuit,
                    bindings,
                    kind="photonic",
                    input_state=self.input_state,
                    shots=self.shots,
                    engine=self.engine,
                    timeout=self.timeout,
                )
                return job["results"]

            def forward(self):
                return self._fn.apply(self.theta, self)

        return _Module(*args, **kwargs)


class SequenceLayer:
    """A parameterised Pulser sequence as a torch Module.

    The analog counterpart of PhotonicLayer: the output is the probability of
    each measured bitstring over the register, with 1 = Rydberg. Same gradient
    method and the same one-job-per-gradient behaviour.
    """

    def __new__(cls, *args: Any, **kwargs: Any):
        torch = _torch()

        class _Module(torch.nn.Module, _ProgramLayer):
            def __init__(
                self,
                client: Any,
                sequence: Any,
                *,
                shots: int = 1000,
                engine: str = "analog.pulser.cpu",
                outcomes: Sequence[str] | None = None,
                init: Sequence[float] | None = None,
                eps: float = 0.01,
                timeout: float = 600.0,
            ) -> None:
                super().__init__()
                self.client = client
                self.sequence = sequence
                self.shots = shots
                self.engine = engine
                self.eps = float(eps)
                self.timeout = timeout
                self.param_names = list(getattr(sequence, "declared_variables", {}) or {})
                if not self.param_names:
                    raise ValueError(
                        "the sequence declares no variables, so there is nothing to "
                        "train. Declare them with seq.declare_variable('name')."
                    )
                start = list(init) if init is not None else [1.0] * len(self.param_names)
                if len(start) != len(self.param_names):
                    raise ValueError(
                        f"init has {len(start)} values for {len(self.param_names)} "
                        f"variables {self.param_names}"
                    )
                self.theta = torch.nn.Parameter(torch.tensor(start, dtype=torch.float32))
                self.outcomes = list(outcomes) if outcomes else self._probe()
                self._fn = _make_function()

            def _probe(self) -> list[str]:
                job = self._submit([self.theta.detach().tolist()])
                return sorted(self._distribution(job[0]))

            def _submit(self, vectors):
                bindings = [dict(zip(self.param_names, v)) for v in vectors]
                job = self.client.run_parametric_sweep(
                    self.sequence,
                    bindings,
                    kind="pulser",
                    shots=self.shots,
                    engine=self.engine,
                    timeout=self.timeout,
                )
                return job["results"]

            def forward(self):
                return self._fn.apply(self.theta, self)

        return _Module(*args, **kwargs)
