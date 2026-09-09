# Release approval and portable skills

For hosted container releases, start with docs/V2-PLATFORM.md: source ZIP intake,
leased trusted build/deploy workers, certified data contracts and the hosted Release
panel. The external-link HMAC flow below is retained for compatibility; it is not
the v2 container worker protocol.

## App release

Register an HTTPS app URL, then use the Release tab to submit:

```json
{
  "version": "1.0.0",
  "queries": ["assembly-readiness@1.0.0"],
  "skills": [],
  "lockfile": {"lockfileVersion": 3, "packages": {"": {"name": "dependency-free-example", "version": "1.0.0"}}}
}
```

The empty dependency example is only valid for a genuinely dependency-free artifact. For real npm apps replace `lockfile` with the **entire** package-lock.json. This beta does not accept workspace links, alternate registries, install scripts, Python requirements or incomplete locks for submitted app packages. Extend policy adapters before supporting those formats; do not omit their dependencies to pass a check.

An administrator must approve every direct and transitive package's exact name, version, sha512 integrity and resolved registry URL. This approval is a policy decision, not an automatic vulnerability or license assessment.

An operator-controlled build job must check out the intended revision, verify the complete manifest/lock, install without unapproved scripts, run tests and security/license/secret checks, build the artifact, and attest **that same artifact**. A convenience signer accepts an npm audit JSON report with zero high/critical findings:

```sh
python scripts/attest.py --manifest release.json --artifact app-build.zip --audit audit.json --output evidence.json
```

Provide `DC_BUILD_SIGNING_KEY` through the trusted job's secret store. The signer does not load `.env`, run scanners or prove that an input report is genuine; the trusted job is responsible for report provenance and all checks. A developer-supplied audit report is not trusted evidence. HMAC means the registry and trusted signer share a key; move to asymmetric attestations/KMS and verified provenance before a broader supply-chain rollout.

Attach `evidence.json` in the Release tab. Evidence must be fresh (24 hours) at approval. A different reviewer approves; owner/editor publishes. Sharing is then available. Each query/skill execution rechecks current package and asset approval. Evidence expiry does not invalidate an already-reviewed release; key rotation does, unless re-attested under the new key.

The signed digest is recorded but Dreamcatcher cannot compare an arbitrary live URL to the artifact. Your deployment pipeline must deploy only that immutable artifact and maintain the URL-to-release binding. For externally hosted apps that can mutate independently, say “registered/published,” not “certified.” This UI deliberately uses Published.

## Skill transfer

ZIP root must contain `SKILL.md` and `manifest.json`. UTF-8 references and scripts may travel, but only `declarative-query-v1` steps execute. Script files are never run in the registry. No LLM execution or automatic package installation is included.

The sample export is the canonical working example. A manifest specifies id, exact version, runtime, inputs, allowed_groups, logical_connections, queries, tools (`queries.run`), empty packages, and 1–10 steps. A step's parameter value may reference `$input.program_id` or a literal. Query parameter types are enforced at execution.

Imports reject traversal, symlinks, encrypted or duplicate files, known secret file types, common credential patterns, excessive file counts/sizes and unsupported runtime fields. This is not a complete DLP solution: review content before export. Destination query references must exist and be approved; skill approval is always local and independent. Logical connection names are metadata; destination query adapters supply actual connection configuration.

Version conflicts return 409. Change version for changed content. Credentials, tokens, source workspace grants and approval records are not part of portable packages.
# Hosted container releases (v2)

Use docs/V2-PLATFORM.md for source ZIP intake, leased trusted build/deploy workers,
certified data contracts and the hosted Release panel. The external-link HMAC flow
below is retained for compatibility; it is not the v2 container worker protocol.
