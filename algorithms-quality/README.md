# Algorithm and Quality Lab

Original, executable Python implementations used to demonstrate data-structure reasoning and test design. The module does not copy coding-challenge statements and does not depend on external services.

## Coverage

| Area | Implementation | Time | Additional space | Trade-off |
|---|---|---:|---:|---|
| Arrays / hash maps | `two_sum` | O(n) | O(n) | Uses memory to avoid a quadratic scan. |
| Strings / hash maps | `longest_unique_substring` | O(n) | O(k) | Tracks the last position of each character. |
| Stacks / queues | `QueueFromStacks` | amortized O(1) | O(n) | A transfer can cost O(n), but each item transfers once. |
| Trees | `BinarySearchTree` | average O(log n), worst O(n) | O(h) traversal | Intentionally unbalanced; duplicates are rejected. |
| Graphs | `shortest_path` | O(V + E) | O(V) | BFS applies to unweighted edges only. |
| Sorting | `merge_sort` | O(n log n) | O(n) | Stable and predictable but not in place. |
| Searching | `binary_search` | O(log n) | O(1) | Caller must provide sorted input. |
| Recursion / backtracking | `permutations` | O(n x n!) | O(n x n!) output | Position-distinct results include duplicates when input values repeat. |
| Dynamic programming | `coin_change` | O(amount x coins) | O(amount) | Finds a count, not the selected coin combination. |

## Quality command

From the repository root:

```powershell
python -m pytest algorithms-quality\tests -q
python -m ruff check algorithms-quality
```

The suite covers empty inputs, duplicates, missing results, invalid values, ordering, mutation safety, deterministic graph traversal, and error behavior.
