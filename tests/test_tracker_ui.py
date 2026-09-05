import re
import time

from playwright.sync_api import expect


def start_site(page, anomaly="Angel Haven"):
    page.select_option("#anomaly", label=anomaly)
    expect(page.locator(".participant-card")).to_contain_text("Playwright Pilot")
    page.click("#startBtn")
    expect(page.locator("#completeBtn")).to_be_visible()
    expect(page.locator("#saveStatus")).to_contain_text("Local data saved")


def complete_site(page):
    page.click("#completeBtn")
    expect(page.locator("#modalBackdrop")).not_to_have_class(re.compile(r"\bhidden\b"))
    expect(page.locator("#modalContent")).to_contain_text("Site complete")


def test_dashboard_loads_and_can_start_without_esi(page):
    expect(page.locator("h1")).to_contain_text("Ratting Tracker")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")
    start_site(page)
    expect(page.locator(".running-head")).to_contain_text("W-16DY")
    expect(page.locator(".running-head")).to_contain_text("Angel Haven")


def test_timer_pause_and_resume(page):
    start_site(page)
    time.sleep(1.15)
    before = page.locator("#timer").inner_text()
    page.click("#pauseBtn")
    expect(page.locator("#pauseBtn")).to_contain_text("Resume Timer")
    paused = page.locator("#timer").inner_text()
    time.sleep(1.15)
    assert page.locator("#timer").inner_text() == paused
    page.click("#pauseBtn")
    expect(page.locator("#pauseBtn")).to_contain_text("Pause Timer")
    time.sleep(2.2)
    assert page.locator("#timer").inner_text() != paused


def test_escalation_sale_value_is_saved_from_completion_modal(page):
    start_site(page)
    complete_site(page)
    page.check("#gotEsc")
    page.select_option("#escName", index=1)
    page.select_option("#escStatus", label="Sold")
    page.click("summary:has-text('Optional details now')")
    page.fill("#escValue", "123456789")
    expect(page.locator("#escValue")).to_have_value("123,456,789")
    page.click("#saveNext")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")

    data = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    assert len(data["recent"]) == 1
    run = data["recent"][0]
    assert run["escalation_status"] == "Sold"
    assert run["escalation_sale_value"] == 123456789
    assert run["escalation_name"]


def test_history_edit_persists_escalation_value(page):
    start_site(page)
    complete_site(page)
    page.click("#skipNext")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")

    page.goto(page.url.rstrip("/") + "/history")
    page.click("button:has-text('Edit')")
    page.select_option("#hEsc", index=1)
    page.select_option("#hStatus", label="Sold")
    page.fill("#hEscValue", "987654321")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")

    page.click("button:has-text('Edit')")
    expect(page.locator("#hStatus")).to_have_value("Sold")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")


def test_complete_and_skip_bonus_returns_immediately_to_next_site(page):
    start_site(page)
    complete_site(page)
    started = time.monotonic()
    page.click("#skipNext")
    expect(page.locator("#startBtn")).to_be_enabled()
    assert time.monotonic() - started < 3.0
    expect(page.locator("#saveStatus")).to_contain_text("Local data saved")


def test_esi_failure_does_not_break_local_tracker(page):
    page.route("**/api/sync", lambda route: route.fulfill(
        status=503,
        content_type="application/json",
        body='{"ok":false,"errors":["simulated ESI outage"]}'
    ))
    page.click("#syncBtn")
    expect(page.locator("#saveStatus")).to_contain_text("Local data safe")
    expect(page.locator("#startBtn")).to_be_enabled()
    start_site(page)


def test_esi_health_warning_is_compact_and_visible(page):
    page.evaluate("""() => {
      DATA.esi.last_error = 'simulated ESI outage';
      DATA.esi.last_success = new Date(Date.now() - 5 * 60 * 1000).toISOString();
      DATA.esi.next_check = new Date(Date.now() + 25 * 60 * 1000).toISOString();
      DATA.esi.pending_runs = 2;
      renderEsiStatus();
    }""")
    expect(page.locator("#esiAlert")).to_be_visible()
    expect(page.locator("#esiAlert")).to_contain_text("ESI-based values may be stale")
    expect(page.locator("#systemStatus")).to_contain_text("Next check")
    expect(page.locator("#systemStatus")).to_contain_text("2 runs pending bounty data")
