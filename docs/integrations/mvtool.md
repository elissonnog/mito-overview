# mvTool Integration

mvTool is implemented in the public mirror as an optional human mtDNA external annotation enrichment layer.

Public-package rule:
- keep the integration optional
- normalize placeholder values before deriving biological summaries
- treat external database annotations as context, not as the sole pathogenicity decision layer
- in the repository's fixture-backed smoke-test path, use the bundled file fixture `tests/fixtures/mock_mvtool_annotations.json`
- in real use, point `MVTOOL_API_URL` to the intended mvTool-compatible endpoint
