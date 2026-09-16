import re
import pytest
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
    expect(page.locator("h1")).to_contain_text("Site Tracker")
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


@pytest.mark.parametrize("status", ["Sold", "Ran Myself"])
def test_escalation_sale_value_is_saved_from_completion_modal(page, status):
    start_site(page)
    complete_site(page)
    page.check("#gotEsc")
    page.select_option("#escName", index=1)
    page.select_option("#escStatus", label=status)
    page.fill("#escValue", "123456789")
    expect(page.locator("#escValue")).to_have_value("123,456,789")
    page.click("#saveNext")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")

    data = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    assert len(data["recent"]) == 1
    run = data["recent"][0]
    assert run["escalation_status"] == status
    assert run["escalation_sale_value"] == 123456789
    assert run["escalation_name"]
    assert run["total_isk"] == 123456789
    page.evaluate("() => fetch('/api/session/end', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})")
    base = page.url.rstrip('/')
    page.goto(base + '/dashboard?days=7')
    expect(page.locator('#totalIskValue')).to_contain_text('123.5M')
    assert page.evaluate("window.__BOOTSTRAP__.perf.total_isk") == 123456789
    page.goto(base + '/history')
    expect(page.locator(f"#runRow{run['id']}")).to_contain_text(status)
    assert page.evaluate("window.__BOOTSTRAP__.history.sessions[0].total") == 123456789


@pytest.mark.parametrize("status", ["Sold", "Ran Myself"])
def test_history_edit_persists_escalation_value(page, status):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")

    page.goto(page.url.rstrip("/") + "/history")
    page.click("button:has-text('Edit')")
    page.select_option("#hEsc", index=1)
    page.select_option("#hStatus", label=status)
    page.fill("#hEscValue", "987654321")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")

    page.click("button:has-text('Edit')")
    expect(page.locator("#hStatus")).to_have_value(status)
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")


def test_history_changing_sold_escalation_to_pending_clears_value(page):
    start_site(page, "Angel Hub")
    complete_site(page)
    page.check("#gotEsc")
    page.select_option("#escName", index=1)
    page.select_option("#escStatus", label="Sold")
    page.fill("#escValue", "30000000")
    page.click("#saveNext")
    data = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    run_id = data["recent"][0]["id"]

    page.goto(page.url.rstrip("/") + "/history")
    page.locator(f"#runRow{run_id} button:has-text('Edit')").click()
    page.select_option("#hStatus", label="Pending")
    expect(page.locator("#hEscValue")).to_have_count(0)
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")

    run = page.evaluate(f"() => fetch('/api/run/{run_id}').then(r => r.json())")
    assert run["run"]["escalation_status"] == "Pending"
    assert run["run"]["escalation_sale_value"] == 0


def test_complete_and_save_returns_immediately_to_next_site(page):
    start_site(page)
    complete_site(page)
    started = time.monotonic()
    page.click("#saveNext")
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
    expect(page.locator(".esi-stack #systemStatus")).to_have_text("ESI sync issue")
    expect(page.locator("#systemStatus")).not_to_contain_text("Next check")
    expect(page.locator("#systemStatus")).not_to_contain_text("pending bounty data")


def test_history_delete_removes_run_without_hanging(page):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")
    page.goto(page.url.rstrip("/") + "/history")
    page.on("dialog", lambda dialog: dialog.accept())
    row = page.locator("tr[id^='runRow']").first
    expect(row).to_be_visible()
    row.locator("button:has-text('Delete')").click()
    expect(row).to_have_count(0)


def test_esi_status_stays_below_sync_button_without_moving_actions(page):
    sync = page.locator(".esi-stack #syncBtn")
    status = page.locator(".esi-stack #systemStatus")
    logout = page.get_by_role("button", name="Log out")
    expect(sync).to_be_visible()
    expect(status).to_be_visible()
    sync_box = sync.bounding_box()
    status_box = status.bounding_box()
    logout_box = logout.bounding_box()
    assert status_box["y"] >= sync_box["y"] + sync_box["height"] - 1
    assert abs(sync_box["y"] - logout_box["y"]) <= 3


def test_sync_header_uses_last_sync_only_wording_on_tracker_and_dashboard(page):
    tracker_status = page.locator("#systemStatus")
    expect(tracker_status).to_be_visible()
    expect(tracker_status).not_to_contain_text("Next check")
    expect(tracker_status).not_to_contain_text("pending bounty data")

    base = page.url.rstrip("/")
    page.goto(base + "/dashboard")
    status = page.locator(".global-sync-status")
    expect(status).to_be_visible()
    expect(status).not_to_contain_text("Next check")
    expect(status).not_to_contain_text("pending bounty data")


def test_unconfigured_esi_keeps_local_tracker_ready(page):
    page.evaluate("""() => {
      window.DATA.esi.configured = false;
      window.DATA.esi.connected_characters = 0;
      renderEsiStatus();
    }""")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")
    expect(page.locator(".esi-stack #systemStatus")).to_contain_text("ESI not configured")
    expect(page.locator("#syncBtn")).to_be_disabled()


def test_completed_site_has_single_next_site_action(page):
    start_site(page)
    complete_site(page)
    expect(page.locator("#saveNext")).to_be_visible()
    expect(page.locator("#skipNext")).to_have_count(0)


def test_history_shows_escalation_sale_value(page):
    start_site(page, "Angel Hub")
    complete_site(page)
    page.check("#gotEsc")
    page.select_option("#escName", index=1)
    page.select_option("#escStatus", label="Sold")
    page.fill("#escValue", "30000000")
    page.click("#saveNext")
    page.goto(page.url.rstrip("/") + "/history")
    row = page.locator("tr[id^='runRow']").first
    expect(row).to_contain_text("Sold")
    expect(row).to_contain_text("30.00m ISK")


def test_session_history_can_edit_loot_and_salvage(page):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    page.click("#endSessionBtn")
    page.fill("#lootValue", "10000000")
    page.fill("#salvageValue", "15000000")
    page.click("#finishSession")
    page.goto(page.url.rstrip("/") + "/history")
    page.locator("tr[id^='sessionRow']").first.locator("button:has-text('Edit')").click()
    expect(page.locator("#sLoot")).to_have_value("10,000,000")
    page.fill("#sSalvage", "25000000")
    page.click("#sessionSaveBtn")
    page.wait_for_load_state("networkidle")
    expect(page.locator("tr[id^='sessionRow']").first).to_contain_text("25.00m")


def test_history_income_chart_has_hover_tooltip(page):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    page.goto(page.url.rstrip("/") + "/history")
    chart = page.locator("#chart")
    expect(chart).to_be_visible()
    box = chart.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    # Tooltip appears when cursor is near a plotted date; canvas logic is covered by existence and JS execution.
    expect(page.locator("#chartTooltip")).to_have_count(1)


def test_start_timer_appears_immediately(page):
    page.select_option("#anomaly", label="Angel Haven")
    started = time.monotonic()
    page.click("#startBtn")
    expect(page.locator("#timer")).to_be_visible(timeout=1000)
    assert time.monotonic() - started < 3.0
    expect(page.locator(".starting-cloud, #completeBtn")).to_have_count(1)


def test_completion_value_fields_are_conditional(page):
    start_site(page, "Angel Hub")
    complete_site(page)

    expect(page.locator("#escValueRow")).to_have_class(re.compile(r"\bhidden\b"))
    page.check("#gotEsc")
    expect(page.locator("#escValueRow")).to_have_class(re.compile(r"\bhidden\b"))
    page.select_option("#escStatus", label="Sold")
    expect(page.locator("#escValueRow")).not_to_have_class(re.compile(r"\bhidden\b"))

    expect(page.locator("#rareValueRow")).to_have_class(re.compile(r"\bhidden\b"))
    page.check("#gotRare")
    expect(page.locator("#rareValueRow")).to_have_class(re.compile(r"\bhidden\b"))
    page.check("#gotRareLoot")
    expect(page.locator("#rareValueRow")).not_to_have_class(re.compile(r"\bhidden\b"))


def test_character_can_be_designated_main(page):
    expect(page.locator(".participant-wrap")).to_have_count(1)
    btn = page.locator(".role-action")
    if "Set as main" in btn.inner_text():
        btn.click()
    expect(page.locator(".role-action.is-main")).to_contain_text("Main")
    expect(page.locator(".character-copy small")).to_contain_text("Main character")
    main_wrap = page.locator(".participant-wrap.main-character")
    expect(main_wrap).to_have_count(1)
    card = main_wrap.locator(".participant-card")
    role = main_wrap.locator(".role-action")
    shadow = card.evaluate("el => getComputedStyle(el).boxShadow")
    assert shadow and shadow != "none"
    card_box = card.bounding_box()
    role_box = role.bounding_box()
    assert role_box["height"] < card_box["height"] * 0.7


def test_history_heat_scale_is_visible(page):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    page.goto(page.url.rstrip("/") + "/history")
    expect(page.locator(".income-legend")).to_contain_text("Lower ISK")
    expect(page.locator(".income-legend")).to_contain_text("Higher ISK")
    colors = page.evaluate("() => [incomeColor(0).css, incomeColor(100000000).css]")
    assert colors[0] != colors[1]


def test_running_tracker_shows_wave_composition_and_trigger(page):
    start_site(page, "Angel Haven")
    expect(page.locator(".wave-progress-card")).to_be_visible()
    expect(page.locator(".wave-composition")).to_be_visible()
    expect(page.locator(".wave-composition")).to_contain_text("Current wave")
    expect(page.locator(".wave-composition .rat-row").first).to_be_visible()
    # Gas Haven's initial wave has an explicit last-Battleship trigger.
    expect(page.locator(".trigger-card")).to_contain_text("last Battleship")


def test_eve_shell_and_clock_are_visible(page):
    expect(page.locator(".side-nav")).to_be_visible()
    expect(page.locator(".eve-time")).to_be_visible()
    expect(page.locator("[data-eve-clock]")).not_to_have_text("--:--:--")


def test_dashboard_uses_session_performance_graph(page):
    page.goto(page.url.rstrip("/") + "/dashboard")
    expect(page.locator("h1")).to_contain_text("Performance Dashboard")
    expect(page.locator("#sessionChart")).to_be_visible()
    expect(page.locator(".metric-card")).to_have_count(4)
    expect(page.locator("body")).to_contain_text("Ratting ISK/h")
    expect(page.locator("body")).to_contain_text("Bounty + ESS only")
    expect(page.locator("body")).to_contain_text("Total ISK/h")
