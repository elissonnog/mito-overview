# TOY-WGS-001

`TOY-WGS-001` is a deterministic whole-genome depth-proxy fixture. The reference contains `MT` and the 22 canonical human autosomes, each 10 bp long. The SAM contains:

- 100 full-length observations at every mitochondrial position;
- 10 full-length observations at every position of `chr1` through `chr5`;
- no reads on `chr6` through `chr22`.

With `NUCLEAR_WINDOW_SIZE=10` and `NUCLEAR_WINDOW_COUNT=5`, the expected values are:

| Metric | Expected value |
|---|---:|
| mt mean depth | 100.0 |
| nuclear-window mean depth | 10.0 |
| mt:nuclear depth ratio | 10.0 |
| requested nuclear windows | 5 |
| valid nuclear windows | 5 |

This fixture validates arithmetic and status handling only. It does not validate biological or diagnostic copy-number accuracy.
