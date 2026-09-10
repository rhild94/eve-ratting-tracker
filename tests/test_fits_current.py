from playwright.sync_api import expect


def test_current_fits_workflow_and_tracker_selector(page):
    # Tracker remains the protected core and still exposes the fit selector.
    expect(page.locator(".side-nav")).to_contain_text("Fits")
    expect(page.locator(".fit-selection-panel")).to_be_visible()
    expect(page.locator(".beta-fit-select")).to_have_count(1)

    base = page.url.rstrip("/")
    page.goto(base + "/?view=fits")
    expect(page.locator("#fitWorkbench")).to_be_visible()

    # Empty library is a deliberate clean state: no dead selector/duplicate/delete controls.
    expect(page.locator(".fit-empty-state")).to_be_visible()
    expect(page.locator(".fit-empty-state")).to_contain_text("No saved fits yet")
    expect(page.locator("#fitSelect")).to_have_count(0)
    expect(page.locator("#fitDuplicate")).to_have_count(0)
    expect(page.locator("#fitDelete")).to_have_count(0)
    expect(page.locator("#fitImport")).to_be_visible()

    # Add one saved fit without depending on external ESI during CI.
    page.evaluate("""async () => {
      const r = await fetch('/api/fits', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          id: 'ci-praxis-fit', ship: 'Praxis', name: 'CI Praxis',
          character_id: null, character_name: 'Unassigned', raw_text: '',
          ship_type_id: null,
          groups: {
            high: [{name: "'Arbalest' Heavy Missile Launcher", quantity: 5, type_id: null}],
            mid: [{name: 'Cap Recharger II', quantity: 5, type_id: null}],
            low: [{name: 'Damage Control II', quantity: 1, type_id: null}],
            rigs: [{name: 'Medium Explosive Armor Reinforcer I', quantity: 3, type_id: null}],
            drones: [{name: 'Republic Fleet Valkyrie', quantity: 5, type_id: null}],
            charges: [{name: 'Caldari Navy Nova Heavy Missile', quantity: 3500, type_id: null}]
          }
        })
      });
      if (!r.ok) throw new Error(await r.text());
    }""")
    page.reload()
    expect(page.locator("#fitSelect")).to_be_visible()
    expect(page.locator("#fitDuplicate")).to_be_visible()
    expect(page.locator("#fitDelete")).to_be_visible()
    expect(page.locator(".eve-fitting-ring")).to_be_visible()
    expect(page.locator(".fit-bays")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("Weapon Calculations")

    # Import flow must still open and remain usable.
    page.click("#fitImport")
    expect(page.locator("#fitImportModal")).to_be_visible()
    expect(page.locator("#fitImportText")).to_be_visible()
    expect(page.locator("#fitImportSave")).to_be_visible()
    page.click("#fitImportClose")

    # The last remaining fit must be deletable and return to the clean empty state.
    page.once("dialog", lambda d: d.accept())
    page.click("#fitDelete")
    expect(page.locator(".fit-empty-state")).to_be_visible()
    expect(page.locator(".fit-empty-state")).to_contain_text("No saved fits yet")
    expect(page.locator("#fitSelect")).to_have_count(0)
    expect(page.locator("#fitDuplicate")).to_have_count(0)
    expect(page.locator("#fitDelete")).to_have_count(0)
