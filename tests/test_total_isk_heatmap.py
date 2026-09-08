from playwright.sync_api import expect


def test_total_isk_heatmap_uses_dashboard_period_and_browser_timezone(page):
    page.goto(page.url.rstrip("/") + "/dashboard?days=7")
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

    page.goto(page.url.rstrip("/") + "/dashboard?days=30")
    panel = page.locator("#totalIskPanel")
    expect(panel).to_be_visible()
    expect(panel.locator(".total-isk-summary span")).to_have_text("30-day total")
    expect(panel.locator("#totalIskCanvas")).to_be_visible()
