# Local battery datasets

Place the downloaded public datasets in this directory using the current
folder names. Raw dataset contents are intentionally ignored by Git because
the extracted files total over 100 GiB. Keep the dataset license, citation,
README, and original directory structure alongside each dataset.

Use `tools/prepare_lfp_dataset.py` from the project root to create compact
derived tables under `results/raw/lfp/`. The initial processing pass reads the
UConn reference performance tests (RPT), the Seville discharge traces, and
inspects the industrial pack CSV. It does not rewrite raw data.

## Label and interpretation limits

- UConn SOH is derived from reference discharge capacity divided by the
  published 1.2 Ah nominal capacity. RUL is cycles to the first observed RPT
  at or below 80% of nominal capacity, so the target is censored for cells
  that do not reach that threshold.
- The UConn pulse resistance is an approximate voltage/current step estimate
  comparing the first pulse sample with the preceding sample. It is not a
  separately measured electrochemical `Re` or `Rct` value.
- Seville SOC is normalized coulomb throughput within each observed discharge
  trace. It assumes each trace spans its measured full discharge and is not an
  independent SOC reference. This single-cell dataset is not evidence of
  cell-to-cell or temperature-generalized SOC accuracy.
- The industrial table contains one eight-cell pack and 3,000 cycle records;
  use it only as supplemental pack-level evaluation, not as an independent
  multi-pack training/test split.

Training and reported validation must split by whole cell (and by pack for the
industrial data), never by randomly splitting adjacent samples from one
trajectory. AI outputs remain research-only and must not participate in the
primary protection path.
