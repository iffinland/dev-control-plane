# Platform packs

Platform packs separate Qortal and Qortium technical contracts. They are routing
and evidence boundaries, not interchangeable copies.

| Pack | Status in Phase 1 | Authority |
| --- | --- | --- |
| [Qortal](qortal/README.md) | Boundary and source reference only | Current Qortal Core/Hub/framework source and observed runtime |
| [Qortium](qortium/README.md) | Boundary and source reference only | Current Qortium Core/Home source and observed runtime |

## Rules

- Never apply a Qortal bridge, identity, QDN or account contract to Qortium, or
  the reverse, because names or request shapes look similar.
- Every skill declares exactly one platform: `qortal`, `qortium` or `shared`.
- Platform source and runtime outrank skills, guides, reports and this control
  plane for claims about implemented behavior.
- Full platform documentation import is deliberately deferred beyond Phase 1.
- Platform packs must not contain credentials, wallet data, private keys or
  private infrastructure configuration.
