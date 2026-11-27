# Writing an operation model

This tutorial describes the evidence-first workflow for adding one operation. An implementation is not adopted merely
because its formula looks plausible: a derivation must be written before the probe, the measured variants must meet the
pre-registered bar, and focused tests must preserve the supported boundary.

## 1. Start with a probe and a derivation

Choose a representative operation and inspect the relevant pandas/NumPy implementation. List every allocation that
could overlap at peak, which output remains live, and which live inputs determine the cost. Write the derivation in the
model module's docstring **before** measuring it.

Create an isolated probe under `docs/benchmarks/<phase>/probes/`. Use a fresh spawned process and the OS peak instrument
with input construction outside the measurement window. Include edge variants that could invalidate the formula (for
example dtype, null share, cardinality, and output shape). Record the measured values and the preregistered acceptance
bar. Do not tune a coefficient after seeing a failed probe and call it a derivation.

`DataFrame.dropna` is a worked example in [dropna.py](../src/nexus/models/dropna.py) and its probe
[p8_dropna.py](benchmarks/phase8/probes/p8_dropna.py). The model derives the mask and retained-row take costs, while the
Phase 8 progress record reports the four-probe adoption result. The v4 `numpy.linspace` attempt is a useful counterexample:
the float32 probe had three live arrays, so the single-output-buffer derivation failed and the operation remained
unestimated. A failed derivation is evidence against adoption, not a reason to fit an unregistered patch.

## 2. Implement the model interface

Add a small module under `src/nexus/models/` and register the model with `@register_model`.

```python
from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class ExampleModel(OperationModel):
    """Derived peak: explain which inputs and temporaries overlap."""

    name = "example"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "example"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if op.receiver is None:
            raise NoEstimateError("receiver is not known")
        # Validate and return only features supported by the derivation.
        return {"rows": 0}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate: ...
```

The example's `features` and `estimate` bodies are intentionally placeholders; never copy them as a model. Follow
existing models such as [dropna.py](../src/nexus/models/dropna.py) for real validation, tiers, range construction, and
cost-driver reporting.

- `matches(op)` should be a cheap syntactic predicate. It does not certify receiver type or arguments.
- `features(op, state)` should validate the receiver, literal arguments, and required descriptors. Refuse unsupported
  cases with `NoEstimateError`; do not invent dimensions or defaults.
- `tier1_features(...)` is optional. Statistics must be bounded, read-only, deterministic where practical, and deadline
  aware. `None` means stay at Tier 0.
- `estimate(features, tier)` must return an `Estimate` with ordered low/expected/high bounds for both RAM and time,
  confidence, tier, and meaningful cost drivers. Reuse shared helpers rather than duplicating calibration policy.

## 3. Test boundaries and the derivation

Add focused tests for a supported input, unsupported arguments or receiver types, estimate ordering, and Tier 1 fallback
or deadline behavior if applicable. Exercise the isolated probe on all preregistered variants; keep the script and
machine-readable output with the benchmark evidence. Then run the focused tests, Ruff, and the regression harness for
the affected model.

Do not silently expand a model's accepted forms to make a notebook look covered. No-estimate behavior is the correct
result when inputs are unknown or an assumption has not been tested. The frozen v4 deferral list and the failures in
[docs/EVALUATION.md](EVALUATION.md) show why: key-dependent hash-table residency, allocation paths, and lazy virtual
pages repeatedly contradicted plausible formulas.

## 4. Freeze discipline

Development results are not held-out validation. Update the phase preregistration before collecting protected data,
record failures as failures, and do not read sealed inputs directly. Once a model tree is frozen, do not edit files in
its manifest; a model change requires a new freeze and a fresh held-out group.
