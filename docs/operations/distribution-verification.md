---
id: distribution-verification
status: stable
last_validated: 2026-07-12
---

# Distribution verification

Run the offline release smoke test before publishing a wheel:

```powershell
python scripts/verify_distribution.py --work-root .distribution-smoke
```

The target must be absent or empty. The verifier builds the wheel from the declared backend without
downloading dependencies, checks packaged schemas, templates, skills, and the console entry point, then
installs the wheel into a fresh virtual environment. Through that installed `science` command it performs
`init`, `validate`, `new`, `run`, `review`, and `campaign-validate` on an independent project.

The verifier intentionally fails rather than reusing a non-empty directory. Its output identifies the
wheel, imported installed package, and generated project. Delete the disposable work root only after
reviewing a failure; it is not scientific evidence.
