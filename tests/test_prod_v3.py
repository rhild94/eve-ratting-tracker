from playwright.sync_api import expect


def base_url(page):
    u = page.url
    return u.split("/dashboard")[0].split("/history")[0].split("/progression")[0].rstrip("/")


def test_global_sync_and_single_fits_navigation(page):
    base = base_url(page)
    for path in ["/", "/dashboard", "/history", "/progression", "/progression?view=characters"]:
        page.goto(base + path)
        expect(page.locator(".eve-time")).to_be_visible()
        expect(page.locator(".global-sync-card")).to_be_visible()
        expect(page.locator(".side-nav a").filter(has_text="Fits")).to_have_count(1)


def test_history_export_is_removed(page):
    page.goto(base_url(page) + "/history")
    expect(page.locator("button").filter(has_text="Export")).not_to_be_visible()


def test_character_details_opens_training_queue_only(page):
    page.goto(base_url(page) + "/progression?view=characters")
    btn = page.locator(".character-card-xl").first.locator("text=View Details")
    expect(btn).to_be_visible()
    btn.click()
    expect(page.locator(".queue-modal")).to_be_visible()
    expect(page.locator(".queue-modal")).to_contain_text("TRAINING QUEUE")
    expect(page.locator(".queue-modal")).not_to_contain_text("Fit Readiness")


def test_progression_uses_site_performance_without_training_snapshot(page):
    page.goto(base_url(page) + "/progression")
    expect(page.locator("#sitePerformanceV3")).to_be_visible()
    expect(page.locator("#sitePerformanceV3 h2")).to_have_text("Site Performance")
    expect(page.locator(".skill-snapshot").first).not_to_be_visible()


def test_angel_hub_trigger_is_protected(page):
    page.goto(base_url(page) + "/")
    page.select_option("#anomaly", label="Angel Hub")
    page.click("#startBtn")
    expect(page.locator("#completeBtn")).to_be_visible()
    expect(page.locator(".trigger-card")).to_contain_text("last Battleship")
