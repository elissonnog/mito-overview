# Reproducibility environment locks

MitoOverview v0.3.0 uses two synchronized Conda records for each supported
release platform:

- `environment-<platform>.yml` is the human-readable exact-version solver
  specification.
- `environment-<platform>.explicit.txt` is the authoritative resolved artifact
  lock. Every artifact URL names an approved conda-forge or bioconda channel
  and ends with the official SHA-256 fragment.

| Platform | GitHub runner |
|---|---|
| `linux-64` | `ubuntu-24.04` |
| `osx-64` | `macos-15-intel` |
| `osx-arm64` | `macos-15` |

CI creates each environment from its matching explicit artifact lock, captures
`conda list --explicit --sha256`, and requires exact URL-plus-hash equality
with the tracked lock. The official release runner and fresh-tag validator
apply the same check to the active parent Conda prefix before creating inherited
wheel or source-distribution test environments. The verifier rejects every
non-comment manifest record that is not an approved SHA-256-bearing HTTPS
artifact and binds its receipt to a clean exact repository commit and tree.
Fresh-tag evidence is generated against the publicly cloned tag checkout, not
an unrelated local lock.

`requirements-release-tools.txt` separately pins the pip-installed release
tools by version and wheel SHA-256. It must be installed with
`pip --require-hashes`. The YAML files remain useful for review and future
solver maintenance, but they are not sufficient release evidence by
themselves.
