# Legacy CLI compatibility

Historical command names remain available for one release-candidate transition. They are hidden from the normal `ainir --help` surface.

| Legacy command | Replacement |
|---|---|
| `ainir trust-gate` | `ainir trust evaluate` |
| `ainir trust-receipt-issue` | `ainir receipt issue` |
| `ainir trust-receipt-replay` | `ainir receipt replay` |
| `ainir negative-conformance-eval` | `ainir conformance negative` |
| `ainir golden-trace-eval` | `ainir conformance golden` |
| `ainir verified-intent-export` | `ainir profile export-intent` |
| `ainir phase18-trust-gate-eval` | `ainir conformance trust-gate` |
| `ainir phase19-trust-receipt-eval` | `ainir conformance receipt` |
| `ainir phase20-receipt-conformance-eval` | `ainir conformance receipt-integration` |
| `ainir phase21-launch-readiness-eval` | `ainir conformance release-readiness` |
| `ainir phase22-verified-intent-eval` | `ainir conformance intent-export` |
| `ainir phase23-verified-intent-hardening-eval` | `ainir conformance intent-hardening` |
| `ainir phase24-verified-intent-semantic-eval` | `ainir conformance intent-semantics` |
| `ainir phase25-verified-intent-contract-eval` | `ainir conformance intent-contract` |
| `ainir phase26-private-trial-eval` | `ainir conformance private-trial` |
| `ainir phase30-v1-rc-candidate-check` | `ainir conformance release-candidate` |

A deprecation warning is sent to standard error. Existing JSON on standard output remains machine-readable. Artifact-producing legacy commands continue to use legacy contract versions so historical scripts and exact receipt replay stay reproducible.
