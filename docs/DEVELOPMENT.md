# Development rules

1. Read `docs/REPOSITORY_CONTRACT.md` before adding files. Application code lives only under `src/somaweave/<package>/`; new top-level packages require a contract update and, if ownership is unclear, a decision record under `docs/decisions/`.
2. Every module ships with tests under `tests/`. Tests never touch the network: provider tests inject recorded transports from `tests/fixtures/providers/`.
3. Domain-model changes: edit `src/somaweave/domain/`, run `python scripts/export_schemas.py`, bump the schema version for breaking changes, add migration notes and update `examples/`. `tests/test_schemas_contract.py` fails if committed schemas drift from the models.
4. Scientific functions are pure and deterministic; document the rule or formula in the docstring and test it with hand-computed values.
5. Evidence handling: keep source-native levels verbatim, cite `evidence_id`s in every claim, label hypotheses, and never let a failed query masquerade as negative evidence.
6. No cluster-specific paths, accounts, user names or secrets in `src/`, `configs/`, `hpc/` templates or tests. `scripts/check_structure.py` enforces this.
7. Before committing: `python -m unittest discover -s tests`, `python scripts/check_structure.py`, `python scripts/export_schemas.py --check`.
8. Commit messages describe the technical change. No authorship-tool branding, generated-content metadata or transcripts anywhere in the repository.
9. Keep documentation synchronized with the code in the same change.
