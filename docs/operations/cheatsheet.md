---
id: cheatsheet
status: stable
last_validated: 2026-07-10
---

# Cheatsheet

```powershell
python -m pip install -e ".[dev]"
science init ../my-research --name "My Research" --id my-research --owner "team"
science --project ../my-research new exp-id --title "Question" --owner "team"
python -m science_repo.cli new exp-id --title "Question" --owner "team"
python scripts/refresh_registry.py
python -m science_repo.cli validate
python -m science_repo.cli run exp-id
python -m science_repo.cli review exp-id
science --project ../my-research campaign-validate campaign-id
python scripts/check_docs.py
pytest
```

Do not run an experiment directly when the output will be cited as evidence; direct execution lacks a
provenance record.
