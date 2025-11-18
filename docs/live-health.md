# Live Health & Papertrade Guard (Phase E)

Phase E adds observability and automatic brakes around `papertrade-live`. This document explains how the workflows fit together, which thresholds drive the decisions, and how to operate the system when an ALERT is raised.

## 1. 全体アーキテクチャ

```
(papertrade-live) --5min--> metrics/trades artifacts
          |                                     ^
          | (health_gate blocks if issue open)  |
          v                                     |
(live-health) --daily--> HEALTH_STATUS / ROLLING_STATUS → Discord/LINE
          |                                      |
          └-- ALERT → GitHub issue `live-health-alert`
```

| Workflow | 役割 | 主な出力 |
| --- | --- | --- |
| `.github/workflows/papertrade-live.yml` | 5 分ごとに `runner/autobot_paper_live.py` を実行し papertrade を行う。Phase E では `health_gate` ジョブを追加し、`live-health-alert` Issue がオープンのときは本番ジョブ（`run`）を skip | papertrade の metrics/trades artifacts |
| `.github/workflows/live-health.yml` | 最新の papertrade artifacts を取得し、`scripts/live_health_report.py` で日次/7日ローリングのヘルス判定。Discord/LINE へレポート、HEALTH\_STATUS / ROLLING\_STATUS を Step output に残し、ALERT のとき `live-health-alert` Issue を作成/更新 | Discord/LINE レポート、`HEALTH_STATUS` / `ROLLING_STATUS`, GitHub Issue |
| `.github/workflows/ci-backtest.yml` （参考） | 戦略の決定論 Gate（net/win/DD/trades）を PR や master でチェック | テキストログ（現状は smoke のみ、将来的に Gate script を組み込み可） |

## 2. `live_health_report.py` が参照するしきい値

`papertrade/config_live.yaml` から読み込む値と、その意味は次の通りです。

| キー | 意味 / 単位 | 使用箇所 | 注意点 |
| --- | --- | --- | --- |
| `risk.daily_max_loss_jpy` | 1 日あたりの許容最大損失（JPY） | 日次 HEALTH 判定（損失がこの値を超えると ALERT）およびローリング損失しきい値の初期値 | 小さくし過ぎると軽微な負けでも ALERT になる。変更時は戦略のボラティリティを考慮すること。 |
| `risk.max_drawdown_pct` | 許容ドローダウン（%） | 日次 HEALTH とローリング DD 判定 | 値を大きくすると下落を長く許容する。 |
| `risk.max_consecutive_losses` | 連敗許容数（回） | 現時点では live-health では未使用（Engine 内で使用）。将来の Gate 追加時の候補 | - |
| `risk.per_trade_risk_jpy` | 1 トレードの許容リスク（JPY） | papertrade 実行側で利用 | - |
| `notify.discord / notify.line` | 通知先 Webhook/Token | live-health で Discord/LINE にレポート送信 | Secrets を必ず設定しておくこと。 |

ローリング判定は `config_live.yaml` に専用キーが無い場合、以下のデフォルトを使用します（`scripts/live_health_report.py` 内部の `rolling_cfg` にて設定）。

| ローリング指標 | デフォルト | 説明 |
| --- | --- | --- |
| ウィンドウ日数 | 7 日 | `--rolling-days` 引数または config 側で上書き可能 |
| ローリング損失しきい値 | `daily_max_loss_jpy` と同値 | 7 日累計損失がこの値を下回ると ALERT |
| ローリング DD | `risk.max_drawdown_pct` と同値 | 期間中の最大 DD が閾値を超えると ALERT |
| ローリング Win Rate | 45% | 勝率がこの値を下回ると WATCH、その他の条件と合わせて ALERT/WATCH を決定 |
| ローリング Trades | max(config の min\_trades, 5) | 期間トレード数が少なすぎる場合は WATCH |

## 3. ALERT が出たときの Runbook

1. **通知の確認**  
   - Discord/LINE の `live_health` レポートを確認し、`HEALTH_STATUS` と `ROLLING_STATUS`、損益/勝率/DD/トレード数を把握する。

2. **GitHub Actions live-health のログ確認**  
   - 該当 run の `Run live health report` ステップにある詳細ログを読み、警告理由（notes）や metrics を確認。

3. **GitHub Issue を確認**  
   - `Issues` → ラベル `live-health-alert` のオープン Issue を開き、いつから Alert か、過去のコメント（原因調査ログなど）を読む。

4. **原因の切り分け**  
   - 市況・戦略変更・設定ミス・実装バグなどを調べる。必要であれば `ci-backtest` やローカル検証を実施。
   - 閾値をいじる前に、根本原因を特定すること。

5. **対応と再開判定**  
   - 問題を修正し、再度 `live-health` が OK/WARN を返す見込みになったら、`live-health-alert` Issue を **手動で Close** する。
   - Issue を閉じるまでは `papertrade-live` の `health_gate` がブロックし続ける点に注意。

6. **再開後の確認**  
   - 次の live-health run を待ち、`HEALTH_STATUS`/`ROLLING_STATUS` が OK/WARN に戻っているか確認。
   - `papertrade-live` Workflow の `run` ジョブが再び実行されていることを GitHub Actions で確認。

> ⚠️ **注意**: 「理由は不明だが再開したいから Issue を閉じる」といった操作はリスクが高い。必ず原因を把握し、再開後の初回実行は手元でも監視する。

## 4. 手動で完全停止 / 再開する方法

- **手動停止したい場合**: GitHub Issue で `live-health-alert` ラベル付き Issue を 1 件作成し、「手動停止のために作成した」と本文に記載する。Issue がオープンの間、`papertrade-live` の `health_gate` により自動トレードは停止される。
- **再開したい場合**: 問題が解消したと判断できたら、該当 Issue を Close する。次の `papertrade-live` 実行分から自動で `run` ジョブが再開される。
- **緊急停止の補助策**: cron を完全に止めたい場合は `.github/workflows/papertrade-live.yml` の schedule 行を一時コメントアウトする方法もある（PR とレビューが必要）。ただし通常は Issue ベースのブロックで十分。

## 5. Workflow メモ

- **`live-health`**  
  - 日次で artifacts を読む → `HEALTH_STATUS` と `ROLLING_STATUS` を算出。`--fail-on-alert` により日次ワークフローが Fail し、同時に `live-health-alert` Issue を管理。

- **`papertrade-live`**  
  - `health_gate` ジョブが Issue を見る → `block=true` ならメイン `run` ジョブを skip。`gate_log` で停止理由をログ出力。これにより Phase E で追加した安全ブレーキが CI レベルで機能する。

この文書を参考に、Phase E で導入した観測と安全装置を運用・改善していってください。必要に応じて Runbook を更新し、将来の Phase でも再利用できるようにしてください。
