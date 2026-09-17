from playwright.sync_api import expect


def base_url(page):
    u = page.url
    return u.split("/dashboard")[0].split("/history")[0].split("/progression")[0].rstrip("/")


def test_global_navigation_shell_clock_and_sync(page):
    base = base_url(page)
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
