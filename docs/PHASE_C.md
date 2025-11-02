# Phase C (Papertrade Integration - Skeleton)
- seed=1729（決定論）
- papertrade/config.yaml … リスクガード閾値（骨）
- CI: .github/workflows/papertrade-smoke.yml
## DoD
- PRが緑（smoke通過）
- 同一seedでmetricsがbaselineと一致
- CI: PyYAML 事前チェック＋リトライ導入、smokeのmetricsをartifact化。
- Legacy workflows: PR発火を抑止（on: pull_request → push: master）、*.bakにバックアップ。
- Notify: urllib.parse未インポートを修正、例外はログのみで失敗にしない（安全）。
- CI: add papertrade-demo (deterministic run + baseline gate). Baseline pinned from local deterministic seed=1729.
- Engine: enforce per-trade loss cap via SL width check (reject entry if over limit).
- Artifacts: artifacts/papertrade_demo/{trades.csv,metrics.csv} uploaded by CI.
## Integration Gate
- Baseline: metrics/baseline_papertrade_integration.csv と一致（決定論 seed=1729）
- Thresholds: net>0, win≥45, DD≤20, trades≥4 を scripts/assert_thresholds.py で検証
## Autobot Gate (improved)
- Thresholds are centralized in ci/thresholds.yaml.
- PR gate uses deterministic --dry, baseline match + YAML thresholds.
- Manual GPT lane: workflow_dispatch, artifacts & step summary, soft thresholds.
