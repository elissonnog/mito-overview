# Reproducibility solver specifications

The three environment files in this directory are exact-version solver inputs
for the supported release platforms. They intentionally do not use Conda's
`@EXPLICIT` URL format: URL/build locks were not generated for foreign
platforms, and package URLs must not be invented. GitHub Actions solves each
file on its matching platform and exports the resulting `conda list --explicit`
record as a CI artifact.

| File | Platform | GitHub runner |
|---|---|---|
| `environment-linux-64.yml` | `linux-64` | `ubuntu-24.04` |
| `environment-osx-64.yml` | `osx-64` | `macos-15-intel` |
| `environment-osx-arm64.yml` | `osx-arm64` | `macos-15` |

These specifications pin release-facing package versions but allow the solver
to select compatible platform build strings. The exported explicit records are
therefore the resolved environment evidence for a particular CI run.
