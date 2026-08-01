# Hypothesis

For the immutable synthetic points in `data/raw/points.csv`, ordinary least squares will recover a
slope of `2` and an intercept of `1`, each within absolute error `1e-12`.

## Falsification

The hypothesis fails if either coefficient exceeds the declared tolerance or if any residual is
non-zero beyond floating-point tolerance.

