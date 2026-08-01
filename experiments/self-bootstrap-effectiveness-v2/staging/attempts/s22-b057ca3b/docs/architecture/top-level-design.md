---
id: top-level-design
status: stable
last_validated: 2026-07-10
---

# Top-level Design

```text
Versioned Framework → Independent Research Projects → Optional Local/HPC/Cloud Platform
```

```mermaid
flowchart LR
  H["Human scientist"] --> C["Coordinating agent / CLI"]
  C --> M["Experiment manifest"]
  C --> S["On-demand specialist skills"]
  M --> X["Local or authorized compute"]
  S --> X
  X --> A["Artifacts + logs"]
  X --> P["Immutable provenance record"]
  A --> R["Reviewer / critic"]
  P --> R
  R --> H
```

## Mental models

- **Experiment directory = scientific transaction:** intent, execution, evidence, and review live together.
- **Manifest = control plane:** it declares the command, outputs, stage, and acceptance criteria.
- **Artifacts + records = data plane:** artifacts communicate results; records prove how they arose.
- **Skills = lazy expertise:** instructions/scripts are loaded only when relevant, keeping context bounded.

The initial implementation is deliberately thin: filesystem contracts plus a Python CLI. Connectors,
HPC adapters, evidence databases, notebook rendering, and rich UI can be added behind these contracts.
