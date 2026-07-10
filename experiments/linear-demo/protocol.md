# Protocol

1. Read the four fixed `(x, y)` observations without modifying the raw file.
2. Fit an ordinary least-squares line using the closed-form estimator.
3. Write numeric results to JSON and render an SVG whose points and line use those same results.
4. Let `science run linear-demo` hash both artifacts and capture the environment.
5. Let `science review linear-demo` verify process success and artifact integrity.

This smoke test validates infrastructure, not scientific generalization.

