# Benchmark Report — $dataset_name

## Dataset Summary

- Ground Truth questions: $sample_count
- Selected prediction records: $prediction_count
- Missing predictions (counted as review): $missing_prediction_count

## Model / Configuration

- Selected model: $selected_model
- Dataset schema version: 0.1
- Model paths: not stored in the schema

## Metrics

| Metric | Result |
|---|---:|
| Answer Exact Match | $exact_match |
| Auto-grade Precision | $precision |
| Auto Coverage | $coverage |
| Review Rate | $review_rate |
| False Auto-Accept rate (recognition mismatch among AUTO_ACCEPT) | $false_auto_accept |

## Performance

- Latency: $latency
- Memory: $memory

## Failure Taxonomy

$failure_taxonomy

Failure details are indexed by sample and question IDs. The archive references source images and does not copy or overwrite them.

## Decision

$decision
