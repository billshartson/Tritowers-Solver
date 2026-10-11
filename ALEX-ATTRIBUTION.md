# Alex CLI/usability workstream provenance

Alex Kendall's validated external patch could not be transferred through the peer channel.

- Author account claim: `dumbie5547` (public account exists; write permission is not verified and no authenticated GitHub connection is available)
- Base: `e2b37753466bd702a9735fe4234d7fbb4a07ec54`
- External patch name: `alex-cli-usability-4396e06f.patch`
- External SHA-256: `b0081e613fce417ae78add90ab6ca7911b8ae543cf776b3e9c4b7c606e83b227`
- Reported scope: README, argparse, board display, undo/correction, EOF handling
- Reported size/tests: 4 files, +329/-43, five CLI tests, fresh-clone checks passed

The local `tritowers_cli.py` and `test_cli.py` are an independent reimplementation from that scope/interface report, not a byte-for-byte copy. Preserve this note when reconciling with Alex's original patch later.

## Upstream maintenance adopted 11 October 2026

The following changes were adapted directly from the shared upstream repository,
[benamoore96/Tritowers-Solver](https://github.com/benamoore96/Tritowers-Solver),
after its `main` reached `f8f734edc73db990bf46e32f330c85c33fac3be5`.
Their author is Sasha Kendall (`dumbie5547`), as recorded in upstream Git history.
This attribution supplements the independently reproduced CLI work described above.

- [`0eaba7f695ab1121a37b5e89981053bb28637ed0`](https://github.com/benamoore96/Tritowers-Solver/commit/0eaba7f695ab1121a37b5e89981053bb28637ed0): the `run_cli` boundary reports EOF on stderr with exit status 1, reports interruption with status 130, and preserves unexpected exceptions and their tracebacks.
- [`2fe422052356db88e7842be6e94fdce2c8bbdc5f`](https://github.com/benamoore96/Tritowers-Solver/commit/2fe422052356db88e7842be6e94fdce2c8bbdc5f): regression tests for normal return, unexpected errors, interruption and subprocess EOF. The subprocess check also has a timeout here.
- [`603eac288b0b090edfad9706f80b838913be14ce`](https://github.com/benamoore96/Tritowers-Solver/commit/603eac288b0b090edfad9706f80b838913be14ce): descriptive names and documentation for the existing heuristic weights, retaining the exact values and scoring policy.

The local CLI's joker support, time budgets, canonical module identity, input
recovery and undo behavior remain in place. The upstream unmerged
`alex/cli-recovery-14-15-30` rewrite was reviewed separately; it was not imported
because replacing the CLI would require reconciling those features first.
