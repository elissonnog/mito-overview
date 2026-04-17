# Release Checklist

## Scientific release goals
- preserve the validated biological logic of the internal mito workflow
- separate core mtDNA interpretation from optional external enrichments
- make the package reproducible outside the MCW HPC layout
- produce documentation that can support both collaborators and manuscript methods text

## Packaging milestones
1. Scaffold public package structure
2. Port shared report utilities
3. Port configuration and path handling
4. Port analysis modules one-by-one from validated internal code
5. Add smoke tests for empty and non-human edge cases
6. Add one example config and one example output bundle
7. Add screenshots and report-page montage to the README
8. Finalize license after dependency and redistribution review
9. Add DOI and citation metadata
10. Freeze preprint figures and tables

## Must-pass checks before GitHub release
- package installs from a clean environment
- CLI returns a valid help or scaffold message
- smoke tests pass locally
- one representative example bundle renders correctly
- optional modules fail gracefully when unavailable
