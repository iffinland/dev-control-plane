# Platform packs

Platform packs separate Qortal and Qortium technical contracts. They are routing
and evidence boundaries, not interchangeable copies.

| Pack | Status | Authority |
| --- | --- | --- |
| [Qortal](qortal/README.md) | Boundary and source reference, plus condensed candidate host/audit notes added 2026-10-31 | Current Qortal Core/Hub/framework source and observed runtime |
| [Qortium](qortium/README.md) | Boundary and source reference only | Current Qortium Core/Home source and observed runtime |

## Rules

- Never apply a Qortal bridge, identity, QDN or account contract to Qortium, or
  the reverse, because names or request shapes look similar.
- Every skill declares exactly one platform: `qortal`, `qortium` or `shared`.
- Platform source and runtime outrank skills, guides, reports and this control
  plane for claims about implemented behavior.
- Full platform documentation import remains deliberately deferred. A condensed
  Qortal host/audit reference was added on 2026-10-31 and is labelled
  `candidate`; it does not change the import boundary or become platform truth.
- Platform packs must not contain credentials, wallet data, private keys or
  private infrastructure configuration.
