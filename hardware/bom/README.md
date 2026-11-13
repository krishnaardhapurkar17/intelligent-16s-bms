# Hardware BOM status

`intelligent_16s_bms_draft.csv` is the current draft BOM for the integrated
five-page schematic. It is not a procurement release: exact orderable parts,
manufacturer part numbers, ratings, and qualification still require review.
No component procurement or population is authorized by this draft. In
particular, the LTC3300-2 active-balancer study is deferred from the build
baseline; do not procure or populate its Wurth 750312504 transformer candidate
without written approval for the intended use or a reviewed replacement.

`afe_16s_draft.csv`, `controller_16s_draft.csv`, and
`power_aux_12v_draft.csv` are legacy page-level exports. Their references,
values, or footprints do not consistently match the current integrated
schematic. Keep them for history only; do not use them to order parts. Regenerate
page-level BOMs from the current integrated design before relying on them.
