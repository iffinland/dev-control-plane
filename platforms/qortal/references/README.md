# Qortal reference notes

Status: **condensed, provenance-labelled reference material** added 2026-10-31.
It is not a full platform-documentation import and it is not platform authority.

Current Qortal Core, Hub and GO source plus observed runtime remain authoritative
for implemented behavior. Load these notes only when a Qortal task needs the
legacy host/audit detail; otherwise use the platform pack and the matching
skill.

## Contents

| Document | Use for | Authority |
| --- | --- | --- |
| [`q-app-host-compatibility.md`](q-app-host-compatibility.md) | Condensed host/bridge/QDN checks for legacy app audits and repairs. | Third-party-derived candidate reference; confirm against current source/runtime. |
| [`legacy-app-audit-checklist.md`](legacy-app-audit-checklist.md) | Operational inventory, compatibility, reproduction and release gates. | A checklist, not proof. |
| [`source-adoption-analysis.md`](source-adoption-analysis.md) | What was adopted, rejected or left unverified from the supplied documents, and Qortal vs Qortium applicability. | Decision record for this integration. |

Related active guidance:

- [Qortal platform pack](../README.md)
- [Legacy dApp audit and repair skill](../../../skills/qortal/legacy-dapp-audit-repair/SKILL.md)
- [Skills library](../../../skills/README.md)
- [Environment and reference freshness gate](../../../ENVIRONMENT.md)
- [Report storage policy](../../../docs/REPORT-STORAGE-POLICY.md)

## Source provenance

The two supplied documents were located and read in full at:

```text
/home/iffi/dev-workspace/docs/references/qortal-development/PROMPT-night-1.md
/home/iffi/dev-workspace/docs/references/qortal-development/QORTAL_Q_APP_MASTER_GUIDE_FOR_LLMS.md
```

| Source | SHA-256 | Use |
| --- | --- | --- |
| `PROMPT-night-1.md` | `2dd0a817612f1954358ca8628953b1929ae8d70ab50da0570dea2912f2f08d60` | Overnight-maintenance practice and legacy defect classes only. Its product scope is Q-Shop+ specific and is not adopted. |
| `QORTAL_Q_APP_MASTER_GUIDE_FOR_LLMS.md` | `9a787b5070571c53ec732c2f94b1116c2d6dd50e8c365ab01ad1287ce2482868` | Third-party host/QDN guide. Claims were classified, not copied wholesale. |

The originals are preserved unmodified in the central reference directory. A
provenance record is stored beside them in
`/home/iffi/dev-workspace/docs/references/qortal-development/PROVENANCE.md`.

## Rules for reuse

1. Check the version pins in the host compatibility note against current
   Core/Hub/GO source and runtime before relying on any claim.
2. Prefer a verified skill's recorded evidence over this note when they differ.
3. Treat every item marked **UNVERIFIED**, **VERSION-SENSITIVE** or
   **CONFLICT** as a question to resolve, not a rule to apply.
4. Do not extend these Qortal notes to Qortium. Validate Qortium behavior
   against Qortium Home/Core source and runtime.
5. Do not copy product-specific commands, paths, branches, design decisions or
   branding from the supplied prompt into global guidance.
6. Never record credentials, wallet data, private keys or private
   infrastructure details in this directory.
