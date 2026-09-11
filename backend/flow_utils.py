def normalize_category(category):
    if category is None:
        return "SAFE"

    normalized = str(category).strip().upper()
    if normalized in {"SAFE", "UNSAFE"}:
        return normalized

    return "SAFE"


def should_route_to_answer(category):
    return normalize_category(category) == "SAFE"
