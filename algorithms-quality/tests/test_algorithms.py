import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms import (  # noqa: E402
    BinarySearchTree,
    QueueFromStacks,
    binary_search,
    coin_change,
    longest_unique_substring,
    merge_sort,
    permutations,
    shortest_path,
    two_sum,
)


def test_arrays_hash_maps_and_strings():
    assert two_sum([4, 7, 4], 8) == (0, 2)
    assert two_sum([], 10) is None
    assert two_sum([1, 2], 10) is None
    assert longest_unique_substring("abba") == "ab"
    assert longest_unique_substring("") == ""
    assert longest_unique_substring("abcade") == "bcade"


def test_queue_from_stacks_preserves_fifo_and_empty_errors():
    queue: QueueFromStacks[int] = QueueFromStacks()
    queue.enqueue(1)
    queue.enqueue(2)
    assert queue.dequeue() == 1
    queue.enqueue(3)
    assert queue.peek() == 2
    assert [queue.dequeue(), queue.dequeue()] == [2, 3]
    assert len(queue) == 0
    with pytest.raises(IndexError):
        queue.dequeue()


def test_binary_search_tree_handles_duplicates_and_traversal():
    tree = BinarySearchTree()
    assert [tree.insert(value) for value in (5, 2, 7, 1, 3)] == [True] * 5
    assert tree.insert(3) is False
    assert tree.contains(7)
    assert not tree.contains(6)
    assert tree.inorder() == [1, 2, 3, 5, 7]
    assert BinarySearchTree().inorder() == []


def test_graph_shortest_path_is_deterministic():
    graph = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}
    assert shortest_path(graph, "a", "d") == ["a", "b", "d"]
    assert shortest_path(graph, "a", "a") == ["a"]
    assert shortest_path(graph, "d", "a") is None


def test_sorting_and_searching_do_not_mutate_input():
    values = [5, -1, 5, 3, 0]
    assert merge_sort(values) == [-1, 0, 3, 5, 5]
    assert values == [5, -1, 5, 3, 0]
    assert merge_sort([]) == []
    assert binary_search([-1, 0, 3, 5], 3) == 2
    assert binary_search([-1, 0, 3, 5], 4) is None
    assert binary_search([], 1) is None


def test_backtracking_permutations():
    assert permutations([]) == [[]]
    assert permutations([1]) == [[1]]
    assert permutations([1, 2, 3]) == [
        [1, 2, 3],
        [1, 3, 2],
        [2, 1, 3],
        [2, 3, 1],
        [3, 1, 2],
        [3, 2, 1],
    ]


def test_dynamic_programming_coin_change_and_validation():
    assert coin_change([1, 3, 4], 6) == 2
    assert coin_change([2], 3) is None
    assert coin_change([2], 0) == 0
    with pytest.raises(ValueError):
        coin_change([0, 1], 4)
    with pytest.raises(ValueError):
        coin_change([1], -1)
