# Contributing

CurvePress Studio is an alpha project for turning images into printable relief plates. Small, reproducible reports and focused pull requests are especially useful.

CurvePress Studioは、画像を印刷可能なレリーフプレートへ変換するアルファ版プロジェクトです。再現手順が明確な不具合報告と、小さく焦点の合った改善提案を歓迎します。

## Before opening an issue / Issueを作る前に

Please check the README and the relevant guide first. Do not attach an image unless you have permission to share it.

画像を共有する権利がない場合は、画像そのものを添付しないでください。READMEと関連ガイドを先に確認してください。

Include as much of the following as possible:

- Operating system and Python version
- CurvePress version or commit
- Input format and pixel dimensions
- Preset/style, plate width and height
- Nozzle diameter, layer height, detail, and contrast
- Exact command or UI action that triggered the problem
- Warning text, traceback, `analysis.json`, or the affected SVG when available
- What you expected and what happened instead

以下の情報があると調査しやすくなります。

- OSとPythonのバージョン
- CurvePressのバージョンまたはコミット
- 入力画像の形式とピクセル寸法
- プリセット、プレートの幅・高さ
- ノズル径、レイヤー高さ、詳細度、コントラスト
- 問題が起きた正確なコマンドまたは画面操作
- 警告文、トレースバック、`analysis.json`、該当SVG
- 期待した結果と実際の結果

## Development setup / 開発環境

Use Python 3.11 or newer:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[cad,dev]"
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e '.[cad,dev]'
```

Run the checks before submitting a pull request:

```bash
pytest
ruff check curvepress tests
```

## Pull requests / Pull Requestの方針

- Explain the user-visible result and why the change is needed.
- Keep changes focused; separate refactors from behavior changes.
- Add or update tests for image-processing, curve-fitting, API, and CAD behavior as appropriate.
- Update documentation when a command, setting, output, or limitation changes.
- Do not commit private images, generated output, the portable runtime, or executables.
- Keep source-image coordinates and aspect ratio stable unless the change explicitly addresses them.

## Geometry and image-processing expectations

For CAD changes, preserve coverage for STEP reload, valid BRep output, single-solid output where applicable, dimensions, zero boundary edges, and zero non-manifold edges.

For image-processing changes, test more than one input style and include cases with uneven paper color, fine lines, and small isolated regions. Explain any intentional change in the resulting contours.

CAD export depends on OpenCascade and may be slower than the SVG-only path. A pull request does not need to include generated CAD files; it should include the smallest reproducible test or fixture instead.

## Language / 言語

Issues and pull requests may be written in English or Japanese. A short English summary alongside Japanese details is helpful for future contributors, but it is not required.

## License

By contributing, you agree that your contributions are provided under the [MIT License](LICENSE).

