# Licensing Notes

## Core repository license
The `mito-overview` core is intended to be released under the MIT License. That license covers the code and documentation in this repository unless a specific file states otherwise.

## External integrations
Two optional human mtDNA enrichments are designed as external integrations rather than bundled dependencies:

1. **Phy-Mer**
   - Phy-Mer is described by its authors as publicly available under the GNU Affero General Public License v3.0 in the original Bioinformatics publication.
   - Source: [Phy-Mer paper (PubMed)](https://pubmed.ncbi.nlm.nih.gov/25505086/)
   - Source: [Phy-Mer paper (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4393525/)
   - In this repository, Phy-Mer should be treated as an optional external tool installed and used separately by the end user.

2. **mvTool**
   - mvTool is exposed through MSeqDR as a web and API resource for mtDNA annotation.
   - The official documentation states that mvTool and associated data are strictly for research use and are not clinically validated or applicable for clinical diagnosis.
   - Source: [mvTool page](https://mseqdr.org/mvtool.php)
   - Source: [mvTool documentation](https://mseqdr.org/wp/index.php/2018/10/17/mseqdr-mvtool-documentation/)
   - In this repository, mvTool should be treated as an optional external annotation service rather than redistributed code or data.

## Practical implication
The clean redistribution model for `mito-overview` is:
- keep the core workflow and reporting code in this repository under MIT
- do not vendor Phy-Mer code into the repository
- do not redistribute mvTool data or imply local ownership of MSeqDR annotation content
- document clearly that optional integrations depend on their own licenses, service terms, and scientific disclaimers

## Release recommendation
Keep external-tool language explicit in the README and methods text. A synthetic public example bundle can be used safely for release as long as private project-specific bundles are not redistributed.
