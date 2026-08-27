# Quality report

The test suite maps one test group to every documented algorithm area and asserts both normal and edge behavior. Tests are deterministic, isolated, and do not use network, filesystem, clock, or random state.

Known limits:

- The binary search tree is educational and unbalanced.
- Generic ordering is expected by sorting and binary-search inputs but is not runtime-enforced.
- Recursive permutation materialization is deliberately bounded by the caller; it is unsuitable for large inputs.
- These implementations are evidence of algorithm and testing fundamentals, not a replacement for optimized standard-library or production graph packages.
