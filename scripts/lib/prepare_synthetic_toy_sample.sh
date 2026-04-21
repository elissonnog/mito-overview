#!/usr/bin/env bash

prepare_synthetic_toy_sample() {
  local repo_root="$1"
  local workdir="$2"

  local dataset_root="${repo_root}/examples/synthetic_data/TOY-001"
  local hv_dir="${workdir}/sample/human_variation"
  local hv_np_dir="${workdir}/sample/human_variation_NP"

  mkdir -p "${hv_dir}" "${hv_np_dir}"

  cp "${dataset_root}/tiny_GRCh38.fa" "${workdir}/tiny_GRCh38.fa"
  samtools faidx "${workdir}/tiny_GRCh38.fa"

  samtools view -bS "${dataset_root}/tiny.sam" | \
    samtools sort -o "${hv_dir}/TOY-001.input.bam"
  samtools index "${hv_dir}/TOY-001.input.bam"

  gzip -c "${dataset_root}/mods.tsv" > "${hv_dir}/TOY-001.wf_mods.1.bedmethyl.gz"
  gzip -c "${dataset_root}/mods.tsv" > "${hv_dir}/TOY-001.wf_mods.2.bedmethyl.gz"
  gzip -c "${dataset_root}/mods.tsv" > "${hv_dir}/TOY-001.wf_mods.ungrouped.bedmethyl.gz"
  gzip -c "${dataset_root}/mods.tsv" > "${hv_np_dir}/TOY-001.wf_mods.bedmethyl.gz"

  bgzip -c "${dataset_root}/phased_snps.vcf" > "${hv_dir}/TOY-001.wf_snp.vcf.gz"
  tabix -f -p vcf "${hv_dir}/TOY-001.wf_snp.vcf.gz"

  bgzip -c "${dataset_root}/np_snps.vcf" > "${hv_np_dir}/TOY-001.wf_snp.vcf.gz"
  tabix -f -p vcf "${hv_np_dir}/TOY-001.wf_snp.vcf.gz"

  bgzip -c "${dataset_root}/np_clinvar.vcf" > "${hv_np_dir}/TOY-001.wf_snp_clinvar.vcf.gz"
  tabix -f -p vcf "${hv_np_dir}/TOY-001.wf_snp_clinvar.vcf.gz"

  cp "${dataset_root}/tiny_mt.gtf" "${workdir}/tiny_mt.gtf"
}


prepare_synthetic_shortread_toy_sample() {
  local repo_root="$1"
  local workdir="$2"

  local dataset_root="${repo_root}/examples/synthetic_data/TOY-001"
  local hv_dir="${workdir}/sample/human_variation"

  mkdir -p "${hv_dir}"

  cp "${dataset_root}/tiny_GRCh38.fa" "${workdir}/tiny_GRCh38.fa"
  samtools faidx "${workdir}/tiny_GRCh38.fa"

  samtools view -bS "${dataset_root}/tiny.sam" | \
    samtools sort -o "${hv_dir}/TOY-SR-001.input.bam"
  samtools index "${hv_dir}/TOY-SR-001.input.bam"

  cp "${dataset_root}/tiny_mt.gtf" "${workdir}/tiny_mt.gtf"
}
