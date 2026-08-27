from collections import deque
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


def two_sum(values: list[int], target: int) -> tuple[int, int] | None:
    """Return the first pair of indices encountered whose values sum to target."""
    seen: dict[int, int] = {}
    for index, value in enumerate(values):
        complement = target - value
        if complement in seen:
            return seen[complement], index
        seen.setdefault(value, index)
    return None


def longest_unique_substring(text: str) -> str:
    """Return the left-most longest substring containing no repeated character."""
    starts: dict[str, int] = {}
    window_start = 0
    best_start = 0
    best_length = 0
    for index, character in enumerate(text):
        previous = starts.get(character)
        if previous is not None and previous >= window_start:
            window_start = previous + 1
        starts[character] = index
        length = index - window_start + 1
        if length > best_length:
            best_start, best_length = window_start, length
    return text[best_start : best_start + best_length]


class QueueFromStacks(Generic[T]):
    def __init__(self) -> None:
        self._incoming: list[T] = []
        self._outgoing: list[T] = []

    def enqueue(self, value: T) -> None:
        self._incoming.append(value)

    def dequeue(self) -> T:
        self._shift()
        if not self._outgoing:
            raise IndexError("dequeue from empty queue")
        return self._outgoing.pop()

    def peek(self) -> T:
        self._shift()
        if not self._outgoing:
            raise IndexError("peek from empty queue")
        return self._outgoing[-1]

    def _shift(self) -> None:
        if not self._outgoing:
            while self._incoming:
                self._outgoing.append(self._incoming.pop())

    def __len__(self) -> int:
        return len(self._incoming) + len(self._outgoing)


@dataclass
class _Node:
    value: int
    left: "_Node | None" = None
    right: "_Node | None" = None


class BinarySearchTree:
    def __init__(self) -> None:
        self.root: _Node | None = None

    def insert(self, value: int) -> bool:
        if self.root is None:
            self.root = _Node(value)
            return True
        node = self.root
        while True:
            if value == node.value:
                return False
            direction = "left" if value < node.value else "right"
            child = getattr(node, direction)
            if child is None:
                setattr(node, direction, _Node(value))
                return True
            node = child

    def contains(self, value: int) -> bool:
        node = self.root
        while node:
            if value == node.value:
                return True
            node = node.left if value < node.value else node.right
        return False

    def inorder(self) -> list[int]:
        result: list[int] = []

        def visit(node: _Node | None) -> None:
            if node is None:
                return
            visit(node.left)
            result.append(node.value)
            visit(node.right)

        visit(self.root)
        return result


def shortest_path(graph: dict[T, set[T]], start: T, goal: T) -> list[T] | None:
    """Find a minimum-edge path in an unweighted graph using breadth-first search."""
    queue: deque[tuple[T, list[T]]] = deque([(start, [start])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        if node == goal:
            return path
        for neighbor in sorted(graph.get(node, set()), key=repr):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, [*path, neighbor]))
    return None


def merge_sort(values: list[T]) -> list[T]:
    if len(values) < 2:
        return values.copy()
    middle = len(values) // 2
    left = merge_sort(values[:middle])
    right = merge_sort(values[middle:])
    merged: list[T] = []
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index] <= right[right_index]:  # type: ignore[operator]
            merged.append(left[left_index])
            left_index += 1
        else:
            merged.append(right[right_index])
            right_index += 1
    return [*merged, *left[left_index:], *right[right_index:]]


def binary_search(sorted_values: list[T], target: T) -> int | None:
    low, high = 0, len(sorted_values) - 1
    while low <= high:
        middle = (low + high) // 2
        if sorted_values[middle] == target:
            return middle
        if sorted_values[middle] < target:  # type: ignore[operator]
            low = middle + 1
        else:
            high = middle - 1
    return None


def permutations(values: list[T]) -> list[list[T]]:
    """Generate position-distinct permutations with recursive backtracking."""
    result: list[list[T]] = []

    def choose(path: list[T], remaining: list[T]) -> None:
        if not remaining:
            result.append(path.copy())
            return
        for index, value in enumerate(remaining):
            choose([*path, value], [*remaining[:index], *remaining[index + 1 :]])

    choose([], values)
    return result


def coin_change(coins: list[int], amount: int) -> int | None:
    """Return the minimum coin count for amount using bottom-up dynamic programming."""
    if amount < 0 or any(coin <= 0 for coin in coins):
        raise ValueError("amount must be non-negative and coins must be positive")
    unreachable = amount + 1
    counts = [0, *([unreachable] * amount)]
    for subtotal in range(1, amount + 1):
        for coin in coins:
            if coin <= subtotal:
                counts[subtotal] = min(counts[subtotal], counts[subtotal - coin] + 1)
    return None if counts[amount] == unreachable else counts[amount]
