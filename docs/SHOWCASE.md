# CurvePress Studio Showcase

## One-line story

**CurvePress Studio turns a photo, drawing, or scan into a smooth, printable relief plate — locally, with a preview and CAD checks.**

**CurvePress Studioは、写真・線画・スキャンを、プレビューとCAD検証付きの滑らかな印刷用レリーフプレートへ、PC上で変換します。**

## The maker workflow

| Step | What happens |
|---|---|
| 1. Choose | Drop in a photo, scan, logo, or drawing |
| 2. Style | Pick woodcut, line art, halftone, poster, or color separation |
| 3. Tune | Set plate size, nozzle, layer height, detail, and contrast |
| 4. Inspect | Compare the source, corrected image, preview, and curves |
| 5. Make | Export SVG, STEP, 3MF, or STL and test-print a small plate |

日本語では、**画像を選ぶ → スタイルを選ぶ → プレビューを確認する → 書き出す → 小さく試し刷りする**という流れです。

## Good first projects

- A high-contrast logo or icon
- A pen drawing or hand-lettered title
- A small ukiyo-e-inspired or engraving-style composition
- A portrait or landscape explored as a circular halftone
- A two- to six-color poster split into separate plates
- A tactile label, stamp, or small art print experiment

## Featured demo: Hokusai to a printable plate

![Hokusai's Great Wave ready for CurvePress](../examples/hokusai-great-wave.jpg)

Start with the included public-domain reproduction of Katsushika Hokusai's *The Great Wave off Kanagawa*. Choose **Woodcut** for a carved-print feel, then compare **Poster** and **Color separation** to show how one historic image can become several different physical plates. The same file is available from the Web UI's **Hokusai sample** button.

The source is [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:The_Great_Wave_at_Kanagawa.jpg), where the artwork and faithful reproduction are marked public domain.

## What makes it different

CurvePress is built around a practical constraint: a beautiful preview is not enough if the geometry cannot survive a nozzle. The pipeline keeps source coordinates, simplifies fragile details, applies conservative minimum widths and gaps, and validates the exported STEP when CAD support is installed.

It is also local-first. That makes experimentation easier for private sketches, school projects, and images that should not be uploaded to an image-processing service.

## Suggested demo

For a clear first demonstration:

1. Use a black-and-white drawing with one or two thin lines.
2. Compare **Line art** and **Woodcut**.
3. Show the corrected preview and curve overlay.
4. Export SVG first, then export CAD with a 0.4 mm nozzle profile.
5. Print a small test plate before scaling up.

This sequence shows the visual transformation and the practical printability checks without implying that every image will produce the same physical result.

## Shareable project description

> CurvePress Studio turns images into printable relief plates. Choose a style, preview the curves, and export SVG/STEP/3MF/STL locally — with nozzle-aware cleanup and CAD validation for a more reliable path from pixels to a physical print.

> CurvePress Studioは画像を印刷用レリーフプレートへ変換します。スタイルを選び、曲線プレビューを確認し、SVG/STEP/3MF/STLを書き出せます。ノズル径に合わせた調整とCAD検証を備え、画像から実物までの流れをローカルで試せます。

## Keep the claims honest

- The project is alpha software; timings and print results vary by machine, material, image, and pressure.
- The app processes locally, but the user remains responsible for the privacy and copyright of input images.
- A successful export is not a guarantee of a successful physical stamp or print.
- Always read warnings and make a small test print first.

