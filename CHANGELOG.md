# Changelog

All notable changes to CurvePress Studio are documented here.

CurvePress is in alpha. Version notes describe the repository state and may not represent a packaged release.

## 0.2.0 — 2026-10-31

### English

- **Pulled proof preview**: simulated print on washi (baren mottling, edge pooling, fibres, per-colour misregistration). Included in the ZIP as `proof-preview.png`.
- **3D plate viewer** (WebGL 2, offline) showing the mirrored physical plate, with plate switching and ×3 relief exaggeration.
- **Kento registration marks** (kagi + hikitsuke) on every colour plate at identical coordinates, in a reserved band clear of the artwork. Toggle in More settings.
- **Colour separation rewritten**: Lab k-means on the real artwork colours, ink colours taken from the image, paper colour excluded, padding outside the artwork never inked.
- Fixed: the paper/background colour used to become its own full-plate "colour", producing a solid frame.
- Fixed: periodic B-spline overshoot on sharp corners could push STEP geometry past the plate; such regions now fall back to the corner-safe Bézier chain.
- Per-layer heightmaps (`<plate>-height.png`) are written with every analysis.

### 日本語

- **刷り上がりプレビュー**：和紙に刷った見た目をシミュレーション（バレンのムラ、縁のインク溜まり、繊維、色ごとのズレ）。ZIPにも `proof-preview.png` として同梱。
- **3D版ビューア**（WebGL 2・オフライン）：鏡像の実物の版を回転表示。版の切り替えと高さ×3強調。
- **見当**（かぎ見当＋引きつけ見当）を全色版の同じ位置に追加。絵にかからない帯を自動確保。「その他の設定」で切り替え可能。
- **色分解を作り直し**：原画の本当の色でLab k-means、インク色は画像から抽出、紙の色は除外、絵の外側の余白は刷らない。
- 修正：紙・背景の色が1色分の版になり、ベタの枠が出ていた問題。
- 修正：鋭い角でBスプラインがはみ出し、STEPが版の外に出ることがあった問題（角に強いベジェに自動切り替え）。

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

