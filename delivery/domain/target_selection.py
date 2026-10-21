"""List membership and count membership are independent of each other.

Inputs must already satisfy current-contract and search conditions. This does
not authorize output or apply partner visibility.
"""


def select_target_ids(current_targets):
    """Rows contain (stable target key, show_in_list, include_in_total)."""
    listed, counted = set(), set()
    for key, show_in_list, include_in_total in current_targets:
        if type(show_in_list) is not bool or type(include_in_total) is not bool:
            raise ValueError("Display and count choices must be explicit booleans.")
        if show_in_list:
            listed.add(key)
        if include_in_total:
            counted.add(key)
    return frozenset(listed), frozenset(counted)
