# Historical pre-review comparison, superseded

These reports and figures retain the first experiment unchanged. At that point,
all policies filtered cheap validation accuracy but did not filter the equally
cheap known analytic latency before selecting a query. Independent review found
that inconsistent feasibility treatment unnecessarily weakened baselines.

The current release uses `benchmarks/search` and the explicit protocol revision
`known_accuracy_and_analytic_latency_screen_v2`. Every policy now filters both
known accuracy and known analytic latency, under the same original 98% accuracy,
2000 LUT, 2 microsecond, 25 MHz constraints and the same 10 seeds and measured-cost
budget. The canonical 40-design corpus was not changed. This folder is historical
research provenance and must not supply the release's performance claims.

The retained `search.py` is the implementation before adding the common latency
filter. Its unrelated live-budget fixes were already under review. Figure source
paths refer to the report directory's name before it was archived here.
