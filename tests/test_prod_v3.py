import re

from playwright.sync_api import expect


def base_url(page):
    u = page.url
    return u.split("/dashboard")[0].split("/history")[0].split("/progression")[0].rstrip("/")


def test_global_navigation_shell_clock_and_sync(page):
    base = base_url(page)

    # Tracker uses the legacy native ESI stack. Verify the final computed layout,
    # not just DOM presence, so a more-specific compatibility rule cannot silently
    # shift Sync ESI out of line with the other top-bar actions again.
    page.goto(base + "/")
    batch_href = page.locator('link[href*="/static/batch1_ui.css"]').get_attribute("href")
    assert batch_href and batch_href.endswith("-batch1-2")
    assert page.locator(".page-tracker .topbar-right").evaluate(
        "el => getComputedStyle(el).alignItems"
    ) == "flex-start"

    sync = page.locator("#syncBtn")
    connect = page.get_by_role("button", name=re.compile("Connect Another Character"))
    logout = page.get_by_role("button", name="Log out")
    clock = page.locator(".eve-time")
    boxes = [el.bounding_box() for el in [sync, connect, logout, clock]]
    assert all(boxes)
    top_edges = [box["y"] for box in boxes]
    assert max(top_edges) - min(top_edges) <= 3

    for path in ["/", "/dashboard", "/history", "/progression", "/progression?view=characters"]:
        page.goto(base + path)
        expect(page.locator(".eve-time")).to_be_visible()
        expect(page.locator(".global-sync-card")).to_be_visible()
        expect(page.locator(".side-nav")).to_be_visible()
        expect(page.locator("[data-eve-clock]")).not_to_have_text("--:--:--")


def test_character_details_opens_training_queue_only(page):
    page.goto(base_url(page) + "/progression?view=characters")
    btn = page.locator(".character-card-xl").first.locator("text=View Details")
    expect(btn).to_be_visible()
    btn.click()
    expect(page.locator(".queue-modal")).to_be_visible()
    expect(page.locator(".queue-modal")).to_contain_text("TRAINING QUEUE")
