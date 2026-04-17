#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-smoke.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

echo "[smoke] repo root: ${REPO_ROOT}"
echo "[smoke] workdir: ${WORKDIR}"
echo "[smoke] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi

HV_DIR="${WORKDIR}/sample/human_variation"
HV_NP_DIR="${WORKDIR}/sample/human_variation_NP"
RUN_ROOT="${WORKDIR}/runs"
FINAL_DIR="${WORKDIR}/final_bundle"
mkdir -p "${HV_DIR}" "${HV_NP_DIR}" "${RUN_ROOT}"

cat > "${WORKDIR}/tiny_GRCh38.fa" <<'EOF'
>MT
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
EOF
samtools faidx "${WORKDIR}/tiny_GRCh38.fa"

cat > "${WORKDIR}/tiny.sam" <<'EOF'
@HD	VN:1.6	SO:coordinate
@SQ	SN:MT	LN:60
r01	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r02	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r03	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r04	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r05	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r06	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r07	0	MT	1	60	20M	*	0	0	AAAAAAAAAAAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r08	0	MT	1	60	20M	*	0	0	AAAAAAAAACAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r09	0	MT	1	60	20M	*	0	0	AAAAAAAAACAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
r10	0	MT	1	60	20M	*	0	0	AAAAAAAAACAAAAAAAAAA	IIIIIIIIIIIIIIIIIIII
EOF
samtools view -bS "${WORKDIR}/tiny.sam" | samtools sort -o "${HV_DIR}/TOY-001.input.bam"
samtools index "${HV_DIR}/TOY-001.input.bam"

cat > "${WORKDIR}/mods.tsv" <<'EOF'
MT	0	1	m	1	+	0	1	0,0,0	10	75	7	3	0	0	0	0	0
MT	9	10	m	1	+	9	10	0,0,0	10	30	3	7	0	0	0	0	0
EOF
gzip -c "${WORKDIR}/mods.tsv" > "${HV_DIR}/TOY-001.wf_mods.1.bedmethyl.gz"
gzip -c "${WORKDIR}/mods.tsv" > "${HV_DIR}/TOY-001.wf_mods.2.bedmethyl.gz"
gzip -c "${WORKDIR}/mods.tsv" > "${HV_DIR}/TOY-001.wf_mods.ungrouped.bedmethyl.gz"
gzip -c "${WORKDIR}/mods.tsv" > "${HV_NP_DIR}/TOY-001.wf_mods.bedmethyl.gz"

cat > "${WORKDIR}/phased_snps.vcf" <<'EOF'
##fileformat=VCFv4.2
##contig=<ID=MT,length=60>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
MT	10	.	A	C	60	PASS	.
EOF
bgzip -c "${WORKDIR}/phased_snps.vcf" > "${HV_DIR}/TOY-001.wf_snp.vcf.gz"
tabix -f -p vcf "${HV_DIR}/TOY-001.wf_snp.vcf.gz"

cat > "${WORKDIR}/np_snps.vcf" <<'EOF'
##fileformat=VCFv4.2
##contig=<ID=MT,length=60>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
MT	10	.	A	C	60	PASS	.
MT	20	.	A	G	50	PASS	.
EOF
bgzip -c "${WORKDIR}/np_snps.vcf" > "${HV_NP_DIR}/TOY-001.wf_snp.vcf.gz"
tabix -f -p vcf "${HV_NP_DIR}/TOY-001.wf_snp.vcf.gz"

cat > "${WORKDIR}/np_clinvar.vcf" <<'EOF'
##fileformat=VCFv4.2
##contig=<ID=MT,length=60>
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="Clinical significance">
##INFO=<ID=CLNDN,Number=.,Type=String,Description="Condition name">
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
MT	10	.	A	C	60	PASS	CLNSIG=Reported;CLNDN=Toy_mito_condition
EOF
bgzip -c "${WORKDIR}/np_clinvar.vcf" > "${HV_NP_DIR}/TOY-001.wf_snp_clinvar.vcf.gz"
tabix -f -p vcf "${HV_NP_DIR}/TOY-001.wf_snp_clinvar.vcf.gz"

cat > "${WORKDIR}/tiny_mt.gtf" <<'EOF'
MT	test	gene	1	60	.	+	.	gene_id "MT-TEST"; gene_name "MT-TEST"; gene_biotype "protein_coding";
MT	test	CDS	1	60	.	+	0	gene_id "MT-TEST"; gene_name "MT-TEST"; gene_biotype "protein_coding";
EOF

cat > "${WORKDIR}/toy.env" <<EOF
PIPELINE_ROOT=${REPO_ROOT}
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_TOY-001
SAMPLE_ID=TOY-001
SOURCE_SAMPLE_DIR=${WORKDIR}/sample
SOURCE_HV_DIR=${HV_DIR}
SOURCE_HV_NP_DIR=${HV_NP_DIR}
REF_FASTA=${WORKDIR}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${HV_DIR}/TOY-001.input.bam
SOURCE_ALIGN_MODE=bam
MT_CONTIG=MT
MT_LENGTH=60
THREADS=1
SPECIES=human
HET_MIN_DEPTH=2
HET_MIN_VAF=0.2
HUMAN_MT_GTF=${WORKDIR}/tiny_mt.gtf
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/toy.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,identity_qc,variant_consequence,circularity_qc,methylation_exploratory,sync_bioinfo

test -f "${FINAL_DIR}/output/report/01_mito_qc.html"
test -f "${FINAL_DIR}/output/report/02_mito_heteroplasmy.html"
test -f "${FINAL_DIR}/output/report/03_mito_deletions.html"
test -f "${FINAL_DIR}/output/report/04_mito_copy_number.html"
test -f "${FINAL_DIR}/output/report/05_mito_feature_annotation.html"
test -f "${FINAL_DIR}/output/report/06_mito_cosegregation.html"
test -f "${FINAL_DIR}/output/report/07_mito_gene_summary.html"
test -f "${FINAL_DIR}/output/report/08_mito_numt_qc.html"
test -f "${FINAL_DIR}/output/report/09_mito_identity_qc.html"
test -f "${FINAL_DIR}/output/report/10_mito_variant_consequence.html"
test -f "${FINAL_DIR}/output/report/11_mito_circularity_qc.html"
test -f "${FINAL_DIR}/output/report/12_mito_methylation_exploratory.html"
test -f "${FINAL_DIR}/sync_manifest.tsv"

echo "[smoke] public pipeline smoke test completed successfully"
