import ast
from pathlib import Path


EXPECTED_ANGEL_ANOMALIES = [
    "Angel Burrow",
    "Angel Hideaway",
    "Angel Hidden Hideaway",
    "Angel Forsaken Hideaway",
    "Angel Forlorn Hideaway",
    "Angel Refuge",
    "Angel Den",
    "Angel Hidden Den",
    "Angel Forsaken Den",
    "Angel Forlorn Den",
    "Angel Yard",
    "Angel Rally Point",
    "Angel Hidden Rally Point",
    "Angel Forsaken Rally Point",
    "Angel Forlorn Rally Point",
    "Angel Port",
    "Angel Hub",
    "Angel Hidden Hub",
    "Angel Forsaken Hub",
    "Angel Forlorn Hub",
    "Angel Haven",
    "Angel Sanctum",
]


def _backend_anomalies():
    source = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ANOMALIES"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("ANOMALIES assignment not found in app.py")


def test_angel_catalog_matches_backend_and_faction_selector():
    assert _backend_anomalies() == EXPECTED_ANGEL_ANOMALIES
    source = Path("static/site_selector.js").read_text(encoding="utf-8")
    for anomaly in EXPECTED_ANGEL_ANOMALIES:
        assert f'anomaly:"{anomaly}"' in source
