# Contributing

Keep IA-RAG Core deterministic, dependency-light, and domain-neutral.

- Add behavior through explicit protocols and injected components.
- Keep plans typed, inspectable, and bound to the execution receipt.
- Use synthetic fixtures for tests and examples.
- Do not add external services to the base runtime.
- Run the public test suite and the reference demo before proposing a change.

Contributions should include tests for plan identity, bounded execution,
evidence/provenance, truth state, and deterministic rendering when those
surfaces are affected.

## Scope and review

Use synthetic fixtures only. Do not add credentials, application data,
production endpoints, or deployment-specific identity integrations. New
runtime behavior must enter through typed plans, neutral protocols, and
explicit dependency injection.

Pull requests should explain the user-visible behavior, identify any changed
public API, and include the relevant test and demo results. Keep changes
focused; architectural or security-sensitive changes require maintainer
review before merge.

## Development checks

From a source checkout, run:

```bash
python -m pip install '.[dev]'
pytest -q
python examples/reference_demo.py
```
