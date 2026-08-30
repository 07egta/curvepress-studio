# Examples

## Featured public-domain artwork

![Katsushika Hokusai — The Great Wave off Kanagawa](hokusai-great-wave.jpg)

`hokusai-great-wave.jpg` is a small, public-domain reproduction of Katsushika Hokusai's *The Great Wave off Kanagawa*. It is included as a ready-to-run Woodcut example so the first result feels like a real printmaking project, not a placeholder graphic.

Source and rights: [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:The_Great_Wave_at_Kanagawa.jpg). The artwork and this faithful reproduction are marked public domain on Commons.

Try it with:

```bash
curvepress convert examples/hokusai-great-wave.jpg --style woodcut --width 139 --height 83 --svg-only -o curvepress-output/hokusai-great-wave
```

The Web UI's **Hokusai sample** button loads the same local file, so you can preview the Woodcut, Poster, and Color separation presets without preparing an image first.

Image regression testing uses the same artwork with the Woodcut preset and reload-checks a 139 × 83 × 2.0 mm STEP with 48 regions and 230 holes. The expected result is one solid, matching dimensions, zero mesh boundary edges, and zero non-manifold edges.

## More classics

| File | Suggested preset | Source and rights |
|---|---|---|
| [mona-lisa.jpg](mona-lisa.jpg) | Photo halftone | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Mona_Lisa.jpg) · public domain |
| [starry-night.jpg](starry-night.jpg) | Color separation | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg) · public domain |

The Web UI shows these as small one-click cards under the featured Hokusai sample. They are intentionally compact so a fresh clone stays quick to download.

