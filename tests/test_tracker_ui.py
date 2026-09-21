import re
import time

from playwright.sync_api import expect


def base_url(page):
    u = page.url
    for marker in ["/dashboard", "/history", "/progression", "/?"]:
        if marker in u:
            u = u.split(marker)[0]
    return u.rstrip("/")


def choose_site(page, anomaly):
    selected = page.locator("#selectedSiteName")
    expect(page.locator("#changeSite")).to_be_visible()
    if selected.inner_text().strip() == anomaly:
        return
    page.click("#changeSite")
    expect(page.locator("#modalContent")).to_have_class(re.compile(r"site-picker-modal"))
    card = page.locator(
        f".site-picker-section:not(.favorites-section) .site-picker-card[data-picker-site='{anomaly}']"
    )
    expect(card).to_have_count(1)
    card.click()
    expect(page.locator("#sitePickerDetail")).to_contain_text(anomaly)
    page.click("#useSelectedSite")
    expect(selected).to_have_text(anomaly)


def start_site(page, anomaly="Angel Haven"):
    choose_site(page, anomaly)
    expect(page.locator(".participant-card")).to_contain_text("Playwright Pilot")
    page.click("#startBtn")
    expect(page.locator("#completeBtn")).to_be_visible()
    expect(page.locator("#saveStatus")).to_contain_text("Local data saved")


def complete_site(page):
    page.click("#completeBtn")
    expect(page.locator("#modalBackdrop")).not_to_have_class(re.compile(r"\bhidden\b"))
    expect(page.locator("#modalContent")).to_contain_text("Site complete")


def test_tracker_start_timer_pause_save_and_wave_helpers(page):
    expect(page.locator("h1")).to_contain_text("Site Tracker")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")
    expect(page.locator("#changeSite")).to_be_visible()
    expect(page.locator("#selectedSiteName")).to_be_visible()

    # The visible selector is the modal/card UI, while the native select remains
    # hidden underneath for compatibility with the existing start payload.
    page.click("#changeSite")
    picker = page.locator("#modalContent")
    expect(picker).to_have_class(re.compile(r"site-picker-modal"))
    expect(picker).to_contain_text("Choose Site")
    hub = picker.locator(".site-picker-section:not(.favorites-section) .site-picker-card[data-picker-site='Angel Hub']")
    haven = picker.locator(".site-picker-section:not(.favorites-section) .site-picker-card[data-picker-site='Angel Haven']")
    sanctum = picker.locator(".site-picker-section:not(.favorites-section) .site-picker-card[data-picker-site='Angel Sanctum']")
    expect(hub).to_contain_text("Tier 8 · Level 1")
    expect(haven).to_contain_text("Tier 9")
    expect(sanctum).to_contain_text("Tier 10 · Level 1")

    haven.click()
    haven.locator(".site-star").click()
    expect(picker.locator(".favorites-section")).to_contain_text("Angel Haven")
    page.click("#useSelectedSite")
    expect(page.locator("#selectedSiteName")).to_have_text("Angel Haven")
    expect(page.locator(".site-favorite-chip")).to_contain_text("Angel Haven")
    dashboard = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    assert dashboard["favorite_sites"] == ["Angel Haven"]

    page.evaluate("""() => {
        const RealDate = Date;
        const skewMs = -120000;
        window.Date = class extends RealDate {
            constructor(...args) {
                if (args.length) super(...args);
                else super(RealDate.now() + skewMs);
            }
            static now() { return RealDate.now() + skewMs; }
        };
    }""")
    started = time.monotonic()
    page.click("#startBtn")
    expect(page.locator("#timer")).to_be_visible(timeout=1000)
    assert time.monotonic() - started < 3.0
    expect(page.locator("#completeBtn")).to_be_visible()
    expect(page.locator("#saveStatus")).to_contain_text("Local data saved")
    expect(page.locator(".running-head")).to_contain_text("W-16DY")
    expect(page.locator(".running-head")).to_contain_text("Angel Haven")
    expect(page.locator(".wave-progress-card")).to_be_visible()
    expect(page.locator(".wave-composition")).to_be_visible()
    expect(page.locator(".wave-composition")).to_contain_text("Current wave")
    expect(page.locator(".wave-composition .rat-row").first).to_be_visible()
    expect(page.locator(".trigger-card")).to_contain_text("last Battleship")

    time.sleep(1.15)
    page.click("#pauseBtn")
    expect(page.locator("#pauseBtn")).to_contain_text("Resume Timer")
    paused = page.locator("#timer").inner_text()
    time.sleep(1.15)
    assert page.locator("#timer").inner_text() == paused
    page.click("#pauseBtn")
    expect(page.locator("#pauseBtn")).to_contain_text("Pause Timer")
    time.sleep(2.2)
    assert page.locator("#timer").inner_text() != paused

    live_parts = [int(x) for x in page.locator("#timer").inner_text().split(":")]
    live_seconds = live_parts[0] * 3600 + live_parts[1] * 60 + live_parts[2]
    complete_site(page)
    modal_time = page.locator(".result-summary > div").first.locator("b").inner_text()
    modal_match = re.fullmatch(r"(\d+)m (\d{2})s", modal_time)
    assert modal_match, modal_time
    modal_seconds = int(modal_match.group(1)) * 60 + int(modal_match.group(2))
    assert abs(modal_seconds - live_seconds) <= 2
    expect(page.locator("#cancelCompletion")).to_be_visible()

    # Complete Site is only a draft/freeze. It must not move the run to History.
    while_open = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    assert while_open["active"] is not None
    assert while_open["recent"] == []
    time.sleep(1.1)
    assert page.locator(".result-summary > div").first.locator("b").inner_text() == modal_time

    page.click("#cancelCompletion")
    expect(page.locator("#modalBackdrop")).to_have_class(re.compile(r"\bhidden\b"))
    expect(page.locator("#completeBtn")).to_be_visible()
    resumed_at = page.locator("#timer").inner_text()
    time.sleep(1.15)
    assert page.locator("#timer").inner_text() != resumed_at

    # Final save completes the run, and the same site remains selected for chaining.
    complete_site(page)
    saved_at = time.monotonic()
    page.click("#saveNext")
    expect(page.locator("#startBtn")).to_be_enabled()
    assert time.monotonic() - saved_at < 3.0
    expect(page.locator("#saveStatus")).to_contain_text("Local data saved")
    expect(page.locator("#selectedSiteName")).to_have_text("Angel Haven")
    expect(page.locator(".site-favorite-chip")).to_contain_text("Angel Haven")

    # Exercise another site through the picker and verify X has the same cancel
    # semantics as the explicit Cancel Completion button.
    start_site(page, "Angel Hub")
    expect(page.locator(".trigger-card")).to_contain_text("last Battleship")
    complete_site(page)
    page.click("#closeResult")
    expect(page.locator("#modalBackdrop")).to_have_class(re.compile(r"\bhidden\b"))
    expect(page.locator("#completeBtn")).to_be_visible()
    active = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    assert active["active"]["anomaly"] == "Angel Hub"
    complete_site(page)
    page.click("#saveNext")

def test_completion_modal_realized_income_statuses_and_conditional_fields(page):
    run_ids = []
    amount = 123456789
    for index, status in enumerate(["Sold", "Ran Myself"]):
        start_site(page)
        complete_site(page)

        if index == 0:
            expect(page.locator("#escValueRow")).to_have_class(re.compile(r"\bhidden\b"))
        page.check("#gotEsc")
        page.select_option("#escName", index=1)
        if index == 0:
            expect(page.locator("#escValueRow")).to_have_class(re.compile(r"\bhidden\b"))
        page.select_option("#escStatus", label=status)
        expect(page.locator("#escValueRow")).not_to_have_class(re.compile(r"\bhidden\b"))

        if index == 0:
            expect(page.locator("#rareValueRow")).to_have_class(re.compile(r"\bhidden\b"))
            page.check("#gotRare")
            expect(page.locator("#rareValueRow")).to_have_class(re.compile(r"\bhidden\b"))
            page.check("#gotRareLoot")
            expect(page.locator("#rareValueRow")).not_to_have_class(re.compile(r"\bhidden\b"))
            page.uncheck("#gotRare")

        page.fill("#escValue", str(amount))
        expect(page.locator("#escValue")).to_have_value("123,456,789")
        page.click("#saveNext")
        expect(page.locator("#trackerContent")).to_contain_text("Start Site")

        data = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
        run = data["recent"][0]
        run_ids.append(run["id"])
        assert run["escalation_status"] == status
        assert run["escalation_sale_value"] == amount
        assert run["escalation_name"]
        assert run["total_isk"] == amount

    page.evaluate("() => fetch('/api/session/end', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})")
    base = base_url(page)
    page.goto(base + "/dashboard?days=7")
    assert page.evaluate("window.__BOOTSTRAP__.perf.total_isk") == amount * 2
    page.goto(base + "/history")
    for run_id, status in zip(run_ids, ["Sold", "Ran Myself"]):
        row = page.locator(f"#runRow{run_id}")
        expect(row).to_contain_text(status)
        expect(row).to_contain_text("123.46m ISK")
    assert page.evaluate("window.__BOOTSTRAP__.history.sessions[0].total") == amount * 2


def test_history_escalation_editing_persists_and_pending_clears_value(page):
    for _ in range(2):
        start_site(page, "Angel Hub")
        complete_site(page)
        page.click("#saveNext")
    data = page.evaluate("() => fetch('/api/dashboard').then(r => r.json())")
    sold_id, ran_id = data["recent"][0]["id"], data["recent"][1]["id"]

    page.goto(base_url(page) + "/history")
    sold_row = page.locator(f"#runRow{sold_id}")
    sold_row.locator("button:has-text('Edit')").click()
    page.select_option("#hEsc", index=1)
    page.select_option("#hStatus", label="Sold")
    page.fill("#hEscValue", "987654321")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")
    expect(page.locator(f"#runRow{sold_id}")).to_contain_text("Sold")
    expect(page.locator(f"#runRow{sold_id}")).to_contain_text("987.65m ISK")

    page.locator(f"#runRow{sold_id} button:has-text('Edit')").click()
    expect(page.locator("#hStatus")).to_have_value("Sold")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")
    page.select_option("#hStatus", label="Pending")
    expect(page.locator("#hEscValue")).to_have_count(0)
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")
    sold = page.evaluate(f"() => fetch('/api/run/{sold_id}').then(r => r.json())")
    assert sold["run"]["escalation_status"] == "Pending"
    assert sold["run"]["escalation_sale_value"] == 0

    page.locator(f"#runRow{ran_id} button:has-text('Edit')").click()
    page.select_option("#hEsc", index=1)
    page.select_option("#hStatus", label="Ran Myself")
    page.fill("#hEscValue", "987654321")
    page.click("#histSaveBtn")
    page.wait_for_load_state("networkidle")
    page.locator(f"#runRow{ran_id} button:has-text('Edit')").click()
    expect(page.locator("#hStatus")).to_have_value("Ran Myself")
    expect(page.locator("#hEscValue")).to_have_value("987,654,321")


def test_esi_failure_health_layout_and_unconfigured_state(page):
    sync = page.locator(".esi-stack #syncBtn")
    status = page.locator(".esi-stack #systemStatus")
    logout = page.get_by_role("button", name="Log out")
    expect(sync).to_be_visible()
    expect(status).to_be_visible()
    expect(status).not_to_contain_text("Next check")
    expect(status).not_to_contain_text("pending bounty data")
    sync_box = sync.bounding_box()
    status_box = status.bounding_box()
    logout_box = logout.bounding_box()
    assert status_box["y"] >= sync_box["y"] + sync_box["height"] - 1
    assert abs(sync_box["y"] - logout_box["y"]) <= 3

    page.route("**/api/sync", lambda route: route.fulfill(
        status=503,
        content_type="application/json",
        body='{"ok":false,"errors":["simulated ESI outage"]}'
    ))
    page.click("#syncBtn")
    expect(page.locator("#saveStatus")).to_contain_text("Local data safe")
    expect(page.locator("#startBtn")).to_be_enabled()
    start_site(page)
    complete_site(page)
    page.click("#saveNext")

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

    base = base_url(page)
    page.goto(base + "/dashboard")
    global_status = page.locator(".global-sync-status")
    expect(global_status).to_be_visible()
    expect(global_status).not_to_contain_text("Next check")
    expect(global_status).not_to_contain_text("pending bounty data")

    page.goto(base)
    page.evaluate("""() => {
      window.DATA.esi.configured = false;
      window.DATA.esi.connected_characters = 0;
      renderEsiStatus();
    }""")
    expect(page.locator("#trackerContent")).to_contain_text("Start Site")
    expect(page.locator(".esi-stack #systemStatus")).to_contain_text("ESI not configured")
    expect(page.locator("#syncBtn")).to_be_disabled()


def test_history_session_edit_and_run_delete(page):
    start_site(page)
    complete_site(page)
    page.click("#saveNext")
    page.click("#endSessionBtn")
    page.fill("#lootValue", "10000000")
    page.fill("#salvageValue", "15000000")
    page.click("#finishSession")

    page.goto(base_url(page) + "/history")
    session_row = page.locator("tr[id^='sessionRow']").first
    session_row.locator("button:has-text('Edit')").click()
    expect(page.locator("#sLoot")).to_have_value("10,000,000")
    page.fill("#sSalvage", "25000000")
    page.click("#sessionSaveBtn")
    page.wait_for_load_state("networkidle")
    expect(page.locator("tr[id^='sessionRow']").first).to_contain_text("25.00m")

    page.on("dialog", lambda dialog: dialog.accept())
    run_row = page.locator("tr[id^='runRow']").first
    expect(run_row).to_be_visible()
    run_row.locator("button:has-text('Delete')").click()
    expect(run_row).to_have_count(0)


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


def test_dashboard_performance_and_total_isk_heatmap(page):
    base = base_url(page)
    page.goto(base + "/dashboard?days=7")
    expect(page.locator("h1")).to_contain_text("Performance Dashboard")
    expect(page.locator("#sessionChart")).to_be_visible()
    expect(page.locator(".metric-card")).to_have_count(4)
    expect(page.locator("body")).to_contain_text("Ratting ISK/h")
    expect(page.locator("body")).to_contain_text("Bounty + ESS only")
    expect(page.locator("body")).to_contain_text("Total ISK/h")

    panel = page.locator("#totalIskPanel")
    expect(panel).to_be_visible()
    expect(panel.locator("h2")).to_have_text("Total ISK")
    expect(panel.locator("#totalIskCanvas")).to_be_visible()
    expect(panel.locator("#totalIskTooltip")).to_have_count(1)
    expect(panel.locator(".total-isk-summary span")).to_have_text("7-day total")
    expect(panel).not_to_contain_text("Brazil (UTC-3)")
    subtitle = panel.locator(".panel-head .muted").inner_text()
    assert "day boundaries" in subtitle
    assert "UTC" in subtitle

    page.goto(base + "/dashboard?days=30")
    panel = page.locator("#totalIskPanel")
    expect(panel).to_be_visible()
    expect(panel.locator(".total-isk-summary span")).to_have_text("30-day total")
    expect(panel.locator("#totalIskCanvas")).to_be_visible()
