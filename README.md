# CurvePress Studio

<div align="center">

**Make a masterpiece you can touch.**

Turn artwork into a printable relief plate with a local, beautiful, three-click workflow.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-111111.svg)](LICENSE)
[![Tests](https://github.com/07egta/curvepress-studio/actions/workflows/test.yml/badge.svg)](https://github.com/07egta/curvepress-studio/actions/workflows/test.yml)
![Status: Beta](https://img.shields.io/badge/status-beta-2563EB.svg)

**English · [日本語](#日本語) · [中文](#中文)**

</div>

> Start with Hokusai's *Great Wave*. In about 30 seconds, turn it into a relief plate you can preview, export, and print.
>
> **[Download the source ZIP](https://github.com/07egta/curvepress-studio/archive/refs/heads/main.zip)** · **[See the showcase](docs/SHOWCASE.md)** · **[Try the examples](examples/)**

## What it does

CurvePress Studio converts artwork, line drawings, photos, and scans into raised plates designed for FDM 3D printing and physical ink transfer. It keeps the source composition in the same coordinates, turns pixels into smooth curves, and checks CAD output before you take it to a slicer.

It is deliberately local: your image is processed on your machine and is not sent to a cloud image service.

### Why CurvePress?

| Starting point | CurvePress result |
|---|---|
| A photo, scan, logo, or drawing | A curve-based printable plate |
| Faded paper or uneven lighting | Corrected contrast and thresholding |
| Fragile details | Nozzle-aware cleanup and minimum line widths |
| A quick visual experiment | Preview SVG plus STEP, 3MF, and STL exports |
| A CAD file you do not want to trust blindly | STEP reload and geometry checks |

### From image to plate

```mermaid
flowchart LR
    A[Image] --> B[Correct]
    B --> C[Trace]
    C --> D[Preview]
    D --> E[Export]
    E --> F[Print & test]
```

## New in 0.3 — faster, simpler

<p align="center"><img src="docs/images/studio.jpg" width="92%" alt="CurvePress Studio: style choices on the left, original and pulled print compared on the printing table"></p>

- **CAD export ~24× faster** (Great Wave woodcut: 7 min → 18 s) and **3MF/STL instantly**, meshed straight from the curves.
- **No Analyze button**: drop or paste an image and the plate follows every change you make.
- **Compare by peeling**: drag across the table to see the original turn into the pulled print.
- A redesigned, trilingual studio with a dark mode and a phone layout.
- Dense halftones can now be saved as 3MF/STL (only STEP has the 1,600-region limit).

## New in 0.2 — from plate to paper

- **Pulled proof** — see the print on washi paper before you print anything: ink mottling from the baren, edge pooling, paper fibres, and a little colour drift between plates.
- **3D plate** — rotate the real, mirrored plate in the browser (WebGL 2, works offline). Switch plates and exaggerate the relief ×3.
- **Kento registration marks** — colour plates get the classic Japanese *kagi* (L) and *hikitsuke* (straight) stops at identical positions, so every colour lands in the same place. A band is reserved so they never touch the art.
<p align="center"><img src="docs/images/proof-hokusai-4color.jpg" width="62%" alt="Simulated 4-colour proof of Hokusai's Great Wave"> <img src="docs/images/plate-3d.jpg" width="34%" alt="3D view of the mirrored plate with kento marks"></p>

- **True-colour separation** — plates now take their ink colours from the artwork (Lab k-means), the paper colour is left uninked, and N colours really means N plates.

## Highlights

- Five practical styles: woodcut, line art, photo halftone, poster, and 2–6 color separation
- Browser input for JPG, PNG, WebP, GIF, BMP, AVIF, and SVG
- Automatic paper-color, white-balance, lighting, and local-contrast correction
- Optional scan-frame removal, small-island removal, hole filling, and printability cleanup
- Nozzle-aware minimum line width, gap, margin, and curve tolerance
- Consistent cubic Bézier curves in SVG and matching cubic B-spline edges in STEP
- Raised flat faces with vertical walls instead of sharp cone-shaped dots
- 15° circular halftone with density-based dot sizing
- STEP reload, BRep validity, solid-count, dimension, closed-mesh, and non-manifold checks
- Local web UI and CLI, with no image upload or external image API

## Quick start

Python 3.11 or newer is required. 3MF, STL and SVG work out of the box; the CAD extra adds STEP export.

```bash
git clone https://github.com/07egta/curvepress-studio.git
cd curvepress-studio
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[cad]"
curvepress serve
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e '.[cad]'
curvepress serve
```

Open <http://127.0.0.1:8765> and choose an image (or paste one). The plate updates by itself as you change the style or size; save 3MF/STL/SVG right away, and click **Also make STEP** only if you need CAD.

For a source checkout without the CAD dependency, use `pip install -e .` and add `--svg-only` to a CLI conversion.

## The five styles

| Style | Good starting point |
|---|---|
| **Woodcut** | Engravings, ukiyo-e-inspired artwork, and scans |
| **Line art** | Pen drawings, lettering, and logos |
| **Photo halftone** | Photos and continuous-tone shading |
| **Poster** | Bold silhouettes and high-contrast icons |
| **Color separation** | Posters and multicolor plates using 2–6 plates |

## One example worth trying

<p align="center">
  <img src="examples/hokusai-great-wave.jpg" width="25%" alt="Katsushika Hokusai's The Great Wave off Kanagawa">
</p>

Start with [Hokusai's *The Great Wave off Kanagawa*](examples/hokusai-great-wave.jpg) and the **Woodcut** preset for bold carved waves and clean contours.

These are compact, public-domain reproductions sourced from [Wikimedia Commons](https://commons.wikimedia.org/). They make the first run instantly recognizable while keeping the repository's demo inputs rights-cleared.

## 30-second masterpiece demo

```bash
git clone https://github.com/07egta/curvepress-studio.git
cd curvepress-studio
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[cad]"
curvepress convert examples/hokusai-great-wave.jpg --style woodcut --width 139 --height 83 --svg-only -o output/hokusai
```

Open `output/hokusai/` to see the curve-based SVG. For the visual workflow, run `curvepress serve`, click **Hokusai sample**, and compare **Woodcut**, **Poster**, and **Color separation** without selecting a file.

## CLI examples

```bash
curvepress convert artwork.png --style woodcut --width 139 --height 83 -o output
curvepress convert photo.jpg --style halftone --width 120 --height 80 -o output
curvepress convert poster.webp --style color_layers --colors 3 -o output
```

The command prints a JSON summary containing the job directory, warnings, metrics, and generated artifacts.

## Print starting point

For a Bambu A1 mini with a 0.4 mm nozzle, start with PLA, 0.20 mm layer height, Arachne wall generation, four walls, five top layers, no supports, and top-surface ironing. CurvePress defaults to a 0.8 mm base, 1.2 mm relief, and 2.0 mm total height for this nozzle size.

Raised artwork receives ink; low areas remain the paper color. Physical results depend on the paper, ink, roller, flatness, and pressure, so begin with a small test print. See the [printing guide](docs/PRINTING.md).

## Source launchers

On Windows, double-click `run_curvepress.bat`. On macOS/Linux, run `sh run_curvepress.command` (macOS may require `chmod +x run_curvepress.command` before double-clicking). Python 3.11+ and internet access are required for the initial dependency installation. Both launchers retry an incomplete setup.

## Portable Windows bundle

The **Windows portable app** GitHub Actions workflow builds `CurvePress-Studio-Windows.zip` and runs a real CAD export using the frozen executable before uploading it. Download the artifact from a successful workflow run, extract the entire ZIP, and double-click `CurvePress/CurvePress.exe`. Keep the `_internal` folder beside the executable. No separate Python installation is needed.

The app opens the local browser UI and saves generated files under `%LOCALAPPDATA%/CurvePress Studio/output`. Keep the console open while using the app; close it to stop the server. This build is unsigned. Source launchers remain available for Windows, macOS, and Linux.

## Documentation

- [Showcase and shareable project story](docs/SHOWCASE.md)
- [Printing and test-print guide](docs/PRINTING.md)
- [Algorithm and design rationale](docs/ALGORITHM.md)
- [Local API](docs/API.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Design boundaries

CurvePress is not an AI image redrawer. It does not intentionally change the source aspect ratio, invent missing composition, or guarantee a successful physical print for every image. It simplifies geometry when details would be too small or fragile for the selected printer settings.

3MF and STL are meshed directly from the same Bézier curves as the SVG (closed and 2-manifold, checked every time) and are ready as soon as the preview is. STEP uses OpenCascade: each contour is one exact C1 B-spline and the reliefs are glued onto the base, which takes seconds to tens of seconds; it is read back and validated, and is skipped above 1,600 isolated regions per layer (3MF/STL still work). Always review warnings and inspect a preview before printing.

The plate size limit is 256 mm; an A1 mini has a 180 × 180 mm bed. Use a plate at most 170 × 170 mm to leave room for adhesion aids. The app warns when a plate exceeds 180 mm. Larger designs require a larger printer; automatic tiling is not implemented.

## Development

```bash
pip install -e '.[cad,dev]'
pytest
ruff check curvepress tests
```

Issues and pull requests are welcome. Please include enough input and configuration detail to reproduce the result, while omitting images you do not have permission to share.

## 日本語

### CurvePress Studioとは

CurvePress Studioは、写真・スキャン・ロゴ・線画を、FDM方式の3Dプリンターで出力できる凹凸プレートへ変換するローカルアプリです。画像の構図を同じ座標で保ちながら、画素を滑らかな曲線に変換し、SVG・STEP・3MF・STLを出力します。

画像は自分のPC上で処理され、クラウドの画像サービスへ送信されません。

### 0.3の新機能 — 速く、かんたんに

- **CAD書き出しが約24倍速く**（北斎・木版画：7分 → 18秒）。**3MF/STLは一瞬**で保存できる
- **解析ボタンなし**：画像を置く（貼り付けもOK）だけで、設定を変えるたびに自動で版が更新
- **めくって見比べ**：境目をドラッグすると、原画が刷り上がりに変わる
- 3か国語・ダークモード・スマホ対応の新しい画面
- 細かい網点も3MF/STLで保存可能に（1,600個の制限はSTEPだけ）

### 0.2の新機能 — 版から紙へ

- **刷り上がり** — 印刷する前に、和紙に刷ったときの見た目を確認（バレンのムラ・縁のインク溜まり・紙の繊維・色ごとの小さなズレ）
- **3D版** — 実物と同じ鏡像の版をブラウザで回して確認（WebGL 2・オフライン動作）。版の切り替え、高さ×3強調つき
- **見当（けんとう）** — 多色版に、伝統木版の「かぎ見当」「引きつけ見当」を全版同じ位置に自動で付ける。紙の角と辺を当てるだけで色がぴったり重なる
- **本物の色で色分解** — 版のインク色を原画の色から自動抽出（Lab k-means）。紙の色は刷らない色として除外し、「N色＝N枚の版」に

### できること

- 木版画、線画、写真ハーフトーン、ポスター、2〜6色分版の5スタイル
- JPG、PNG、WebP、GIF、BMP、AVIF、SVGの読み込み
- 紙色・ホワイトバランス・照明ムラ・局所コントラストの自動補正
- スキャン枠の除去、小さすぎる島や穴の整理、ノズル径に合わせた印刷可能性の調整
- SVGのプレビューと、STEP・3MF・STLの書き出し
- STEPの再読み込み、BRep、寸法、ソリッド数、メッシュ境界のチェック
- ブラウザーUIとコマンドラインの両方に対応

### 最短で試す

Python 3.11以上を用意し、上の **Quick start** の手順で起動してください。ブラウザーで <http://127.0.0.1:8765> を開き、画像を選ぶ（貼り付けでもOK）だけ。スタイルやサイズを変えると自動で版が更新されます。3MF/STL/SVGはすぐ保存でき、CAD用のSTEPはボタンで作れます。

詳しい印刷条件は[印刷ガイド](docs/PRINTING.md)、処理の考え方は[アルゴリズムの説明](docs/ALGORITHM.md)を参照してください。

### 開発への参加

不具合報告や改善提案は歓迎します。画像を共有できない場合でも、画像形式・解像度・プリセット・ノズル径・警告文を添えてください。詳しくは[CONTRIBUTING.md](CONTRIBUTING.md)をご覧ください。

## 中文

CurvePress Studio 可以把照片、扫描件、线稿和海报转换成适合FDM 3D打印的浮雕版。图像在本地处理，不会上传到云端图像服务。

从 `examples/` 中选择葛饰北斋、蒙娜丽莎或《星月夜》，在网页界面点击 **Hokusai sample** 或对应的示例卡片，然后比较木刻、照片半色调和颜色分离效果。最后可以导出 SVG、STEP、3MF 和 STL。

**0.2 新功能：** 和纸印刷效果预览、可旋转的 3D 版面、多色版自动添加日本木版传统的规矩（套准标记）、按原画真实颜色分色。

项目支持日本語、English 和中文界面，欢迎提交 Issue 或 Pull Request。

## License

MIT License. See [LICENSE](LICENSE).


