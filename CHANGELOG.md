# Changelog

## 0.2.0 — 2026-10-31

- Validate and convert numeric settings from the browser; reject invalid or nonfinite dimensions and preserve zero margins.
- Keep transparent images on a white background and preserve blank white inputs.
- Invalidate previous results when inputs change; ignore stale image, analysis, and export responses.
- Match CAD faces to the SVG cubic Bezier chains and preview the actual curve orientation.
- Speed up halftone rasterization and connected-component/hole cleanup without changing pixels.
- Honor the scan-frame switch; show actual quantized ink colors and an A1 mini bed-size warning.
- Serialize CAD work, reserve export jobs atomically, publish only complete validated exports, and download analysis ZIPs before CAD.
- Bundle sample assets in wheels, repair interrupted launcher setup, and add CAD/packaging CI.


All notable changes to CurvePress Studio are documented here.

CurvePress is in alpha. Version notes describe the repository state and may not represent a packaged release.

## Unreleased

### Documentation / ドキュメント

- Reworked the README as a bilingual, quick-scan project landing page.
- Added a concise showcase page for makers, printmakers, and 3D-printing users.
- Clarified local processing, portable-bundle boundaries, output formats, and print-test expectations.
- Rewrote the contribution guide with reproducible issue and pull-request guidance.

## 0.1.1 — 2026-08-29

### English

- Added a Windows `Start.exe` one-click launcher.
- Added a portable Python/CAD runtime bundle for no-install startup.
- Kept `Open_CurvePress.bat` as a visible-console fallback.

### 日本語

- Windows用のワンクリック起動ランチャー `Start.exe` を追加。
- インストールなしで起動できるPython/CADランタイム同梱版を追加。
- 黒いコンソール画面で確認できる代替起動方法として `Open_CurvePress.bat` を維持。

## 0.1.0 — 2026-08-29

### English

- First public-ready architecture.
- Five image styles, including 2–6 color plates.
- Shape-preserving cubic Bézier SVG and B-spline STEP.
- Automatic nozzle-aware cleanup and plate dimensions.
- STEP read-back, BRep, dimension, and closed-mesh validation.
- Local web UI and CLI.

### 日本語

- 公開用の基本アーキテクチャを整備。
- 2〜6色のプレートを含む5種類の画像スタイルに対応。
- 形状を保ちやすい三次ベジェSVGとBスプラインSTEPに対応。
- ノズル径に合わせた自動クリーンアップとプレート寸法調整。
- STEP再読み込み、BRep、寸法、閉じたメッシュの検証に対応。
- ローカルWeb UIとCLIを追加。


