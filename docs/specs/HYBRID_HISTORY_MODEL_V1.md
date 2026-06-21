# Hybrid History Model V1

## Summary

- The current engine remains rule-led for final indicator state labels.
- Historical time-series data now drives a parallel statistical lane.
- The statistical lane adds regime-aware baselines, rolling features, anomaly scores, agreement flags, and hybrid severity.

## Config

- File: `config/history_model.yaml`
- Key fields:
  - `anchor_tag`
  - `regime_quantiles.low_max`
  - `regime_quantiles.high_min`
  - `parameters.min_samples_per_regime`
  - `parameters.min_samples_global`
  - `parameters.trend_short_window`
  - `parameters.trend_long_window`
  - `parameters.persistence_cap_points`
  - `parameters.robust_z_clip`
  - `parameters.fusion_weight`
  - `parameters.enter_exit_hysteresis`
  - `parameters.hybrid_aggregation_enabled`
  - `cache.path`
  - `key_indicator_tags`

## Backend Outputs

- `baseline_profile.history_model_metadata`
  - `profile_source`
  - `anchor_tag`
  - `regime_cut_points`
  - `selected_regime`
  - `global_fallback_used`
  - `hybrid_aggregation_enabled`

- `features.per_tag[tag]`
  - `slope_7`
  - `slope_30`
  - `ewma_deviation`
  - `rolling_std`
  - `rolling_range`
  - `run_length`
  - `change_point_index`

- `abnormal_details[*]`
  - `selected_regime`
  - `robust_z_score`
  - `directed_tail_score`
  - `statistical_anomaly_score`
  - `statistical_state`
  - `agreement_flag`
  - `hybrid_severity_score`

- `calculation_audit`
  - `history_model_metadata`
  - `indicators[*].selected_regime`
  - `indicators[*].regime_sample_count`
  - `indicators[*].global_sample_count`
  - `indicators[*].robust_z_score`
  - `indicators[*].statistical_anomaly_score`
  - `indicators[*].statistical_state`
  - `indicators[*].agreement_flag`
  - `indicators[*].hybrid_severity_score`
  - `subsystems[*].hybrid_avg_severity`
  - `subsystems[*].history_warning_count`
  - `subsystems[*].conflict_indicator_count`
  - `plant.hybrid_max_severity`
  - `plant.history_warning_count`
  - `plant.conflict_indicator_count`
  - `plant.risk_upgrade_applied`

- `analysis_result.history_model_metadata`
- `websocket result.data.history_model_metadata`

## Runtime Behavior

- `build_baseline_profile` prefers a cached history profile when the data signature matches.
- If no matching cache exists, the profile is built at runtime and marked `profile_source=runtime`.
- Regime-specific samples are filtered for standby paired expanders so idle rows do not pollute the normal profile.
- `hybrid_aggregation_enabled=false` keeps existing risk logic unchanged.
- `hybrid_aggregation_enabled=true` allows a one-level risk upgrade when a key indicator is `statistical_state=high` and its persistence is at least 6 points.

## Offline Cache Builder

- Script: `scripts/build_history_profiles.py`
- Example:

```bash
python scripts/build_history_profiles.py data/demo.xlsx --output tmp/history_profiles.json
```
