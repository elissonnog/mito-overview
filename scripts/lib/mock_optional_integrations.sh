#!/usr/bin/env bash

mock_phymer_root() {
  local repo_root="$1"
  printf '%s\n' "${repo_root}/tests/fixtures/mock_phymer_vendor"
}

mock_mvtool_fixture_url() {
  local repo_root="$1"
  printf 'file://%s\n' "${repo_root}/tests/fixtures/mock_mvtool_annotations.json"
}
