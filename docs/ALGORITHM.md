# Algorithms and Design Rationale

CurvePress does not try to redraw an image artistically. It preserves the source composition in the same coordinates while converting it into a curve-based raised plate that can exist on an FDM printer.

## Processing pipeline

1. Apply EXIF rotation, composite transparency over white, and fit the image to the plate while preserving its aspect ratio.
2. Correct paper color and white balance, remove low-frequency lighting variation, and enhance local contrast.
3. Apply style-specific color separation and thresholding.
4. Remove only known image-placement borders, then remove nozzle-sized islands, fill tiny holes, and thicken lines only as needed for printability.
5. Extract the 0.5 contour and simplify it within tolerance using Ramer–Douglas–Peucker.
6. Convert the contour to a self-intersection-resistant cubic Bézier sequence with rounded corners inside local triangles.
7. Write SVG and convert the same curves into exact cubic B-spline edges before extruding with OpenCascade.
8. Fuse the base and raised faces, write STEP, and reload it.
9. Check BRep validity, solid count, physical dimensions, STL boundaries, and non-manifold edges.

## Referenced research and implementations

### Contours and curves

- Peter Selinger, **Potrace: a polygon-based tracing algorithm**. The bitmap-to-intermediate-polygon-to-smooth-Bézier structure is used as a reference. <https://www.mathstat.dal.ca/~selinger/potrace/potrace.pdf>
- Philip J. Schneider, **An Algorithm for Automatically Fitting Digitized Curves**, *Graphics Gems*, 1990. A classic method for approximating curves with controlled cubic Bézier error. <https://dl.acm.org/doi/10.5555/90767.90941>
- VTracer. Its practical clustering, hierarchy, and curve-tracing pipeline for photos and color images is used as a reference. <https://github.com/visioncortex/vtracer>
- SVG 2 Paths. The emitted `C` command follows the W3C cubic Bézier path definition. <https://www.w3.org/TR/SVG2/paths.html>

CurvePress does not use an unconstrained Catmull–Rom conversion because its control points can bulge outside a contour and self-intersect a CAD face. It uses a 24% corner-rounding interval before exactly degree-elevating a quadratic Bézier inside a local triangle. The remaining edges are represented as collinear cubic Béziers, so the complete SVG consistently uses four control points per segment.

### Local binarization

- J. Sauvola and M. Pietikäinen, **Adaptive document image binarization**, *Pattern Recognition* 33(2), 2000. Used for local thresholds on uneven backgrounds. <https://doi.org/10.1016/S0031-3203(99)00055-2>
- The scikit-image Sauvola example was used to verify the equation and practical parameters. The implementation itself is independent and uses NumPy/SciPy. <https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_niblack_sauvola.html>

### CAD validation

- OpenCascade `BRepCheck` is used to validate faces, extrusions, and the final solid. <https://dev.opencascade.org/doc/refman/html/package_brepcheck.html>
- `STEPControl_Writer` and `STEPControl_Reader` reload the exported STEP file for verification. <https://dev.opencascade.org/doc/refman/html/package_stepcontrol.html>

## Automatic physical settings

When nozzle diameter is `d` and layer height is `h`, unspecified values use these starting rules:

- Base thickness: `layer_round(max(0.8, 2d), h)`
- Relief height: `layer_round(max(1.0, 3d), h)`
- Minimum line width and gap: `max(0.5, 1.25d)`
- Outer margin: `max(2.0, 5d)`
- Curve tolerance: varies from `0.055–0.18 mm` with nozzle diameter and detail

These are conservative starting rules that keep slicer-impossible details out of the CAD model. Arachne-style variable line width improves thin-wall reproduction, but it cannot make zero-width geometry or isolated points printable. The Arachne concept was also cross-checked against Ultimaker's explanation. <https://ultimaker.com/learn/get-an-engine-boost-with-ultimaker-cura-and-arachne-beta/>

## Style presets

| Preset | Main processing | Best for |
|---|---|---|
| Woodcut | Otsu dark regions + Sauvola lines + gradient contours | Ukiyo-e, engraving, scans |
| Line art | Local Sauvola threshold | Pen drawings, lettering, logos |
| Photo halftone | 15° circular dots with density-based diameter | Photos, shading |
| Poster | Strong Otsu two-tone threshold | Silhouettes, icons |
| Color separation | 2–6 colors with median-cut | Multicolor plates, posters |

## Deliberately not done

- AI redraw of the composition
- Changing the source aspect ratio
- Sharp cone-shaped or pyramid-shaped dots
- Accepting an unreadable STEP or an open mesh
- Unlimited triangle growth just to preserve every detail

