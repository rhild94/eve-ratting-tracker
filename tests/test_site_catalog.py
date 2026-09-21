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


    expected_ratings = {
        "Angel Hideaway": (1, 1),
        "Angel Hidden Hideaway": (1, 2),
        "Angel Forsaken Hideaway": (1, 3),
        "Angel Forlorn Hideaway": (1, 4),
        "Angel Burrow": (2, None),
        "Angel Refuge": (3, None),
        "Angel Den": (4, 1),
        "Angel Hidden Den": (4, 2),
        "Angel Forsaken Den": (4, 3),
        "Angel Forlorn Den": (4, 4),
        "Angel Yard": (5, None),
        "Angel Rally Point": (6, 1),
        "Angel Hidden Rally Point": (6, 2),
        "Angel Forsaken Rally Point": (6, 3),
        "Angel Forlorn Rally Point": (6, 4),
        "Angel Port": (7, None),
        "Angel Hub": (8, 1),
        "Angel Hidden Hub": (8, 2),
        "Angel Forsaken Hub": (8, 3),
        "Angel Forlorn Hub": (8, 4),
        "Angel Haven": (9, None),
        "Angel Sanctum": (10, 1),
    }
    for anomaly, (tier, level) in expected_ratings.items():
        level_src = "null" if level is None else str(level)
        assert f'anomaly:"{anomaly}",tier:{tier},level:{level_src}' in source
