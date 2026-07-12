---
id: cheatsheet
status: stable
last_validated: 2026-07-12
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
science --project ../my-research transition exp-id --to designed --reason "Protocol preregistered" --actor agent-id
science --project ../my-research campaign-validate campaign-id
science --project ../my-research task-claim campaign-id task-id --worker agent-1
science --project ../my-research task-heartbeat campaign-id task-id --worker agent-1 --token TOKEN
science --project ../my-research task-release campaign-id task-id --worker agent-1 --token TOKEN --outcome completed
science --project ../my-research handoff-validate campaign-id path/to/handoff.json
science --project ../my-research campaign-status campaign-id --max-attempts 3
science --project ../my-research dispatch-envelope campaign-id task-id > dispatch.json
science --project ../my-research dispatch-audit campaign-id dispatch.json handoff.json
science --project ../my-research cohort-validate experiment-id --campaign campaign-id
science --project ../my-research cohort-plan experiment-id subject-1 subject-2 subject-3 subject-4 subject-5 --campaign campaign-id
science workspace-create subject-1 COMMIT --repository D:\repo --sessions-root D:\science-sessions
science workspace-remove subject-1 --repository D:\repo --sessions-root D:\science-sessions
python scripts/check_docs.py
pytest
```

Do not run an experiment directly when the output will be cited as evidence; direct execution lacks a
provenance record.

Treat task lease tokens as ephemeral coordinator capabilities. Do not commit them or place them in a
handoff. Campaign runtime directories are operational state, not scientific evidence.

`dispatch-envelope` prepares a contract for the main agent to pass to the platform's native subagent
primitive; it does not spawn an agent. Require a structured handoff and pass `dispatch-audit` before
integration. A review agent must be independent of the work it reviews.

Create cohort assignment ledgers before inspecting outcomes. `workspace-remove` delegates to Git and
does not recursively delete session directories; use `--force` only after reviewing uncommitted work.
