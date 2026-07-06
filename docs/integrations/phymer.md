# Phy-Mer Integration

Phy-Mer is implemented in the public mirror as an optional human mtDNA haplogroup enrichment layer.

Public-package rule:
- keep haplogroup calling optional
- keep species gating explicit
- do not make this dependency mandatory for the reproducible core workflow
- in the repository's fixture-backed smoke-test path, use the bundled deterministic fixture under `tests/fixtures/mock_phymer_vendor`
- in real use, point `PHYMER_ROOT` to a true local Phy-Mer vendor tree
