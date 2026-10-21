"""Initial selections approved by the user; never overwrite an existing choice."""

def initial_count_inclusion(target_kind: str) -> bool:
    if target_kind == "customer":
        return True
    if target_kind == "site":
        return False
    raise ValueError("Expected customer or site.")
