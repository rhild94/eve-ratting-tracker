from playwright.sync_api import expect


def test_current_fits_workflow_and_tracker_selector(page):
    # Tracker remains the protected core and still exposes the fit selector.
    expect(page.locator(".side-nav")).to_contain_text("Fits")
    expect(page.locator(".fit-selection-panel")).to_be_visible()
    expect(page.locator(".beta-fit-select")).to_have_count(1)

    # Current Fits workflow: saved fits + import-driven management.
    page.goto(page.url.rstrip("/") + "/?view=fits")
    expect(page.locator("#fitWorkbench")).to_be_visible()
    expect(page.locator("body")).to_contain_text("Saved Fits")
    expect(page.locator("#fitSelect")).to_be_visible()
    expect(page.locator("#fitImport")).to_be_visible()
    expect(page.locator("#fitDuplicate")).to_be_visible()
    expect(page.locator("#fitDelete")).to_be_visible()

    # Open the import flow to catch regressions where the control exists but does nothing.
    page.click("#fitImport")
    expect(page.locator("#fitImportModal")).to_be_visible()
    expect(page.locator("#fitImportText")).to_be_visible()
    expect(page.locator("#fitImportSave")).to_be_visible()
