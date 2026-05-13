# job_scout/application/_form_helpers.py
"""Shared form-fill helpers for ATS Playwright drivers.

Used by greenhouse_form.py, lever_form.py, ashby_form.py.

All helpers are designed to be safe-by-default: they prefer no-op over
guessing, never type into combo-boxes, and never click submit. Each driver
remains responsible for its own apply_url navigation + standard-field fill.
"""

from typing import Dict, List


# ── Common question keywords + canonical answers ───────────────────────────

def fill_common_questions(page, profile: Dict):
    """Answer common application questions with safe canonical values.

    Designed for forms that use either native <select> or react-select-style
    combo-boxes. Tries each known phrasing in turn — no-op when the form
    doesn't include the question.
    """
    country = (profile.get("country") or "").strip() or "India"

    answer_question(page, ["authorized to work", "right to work", "work authorization"], "Yes")
    answer_question(page, ["sponsorship", "visa sponsor", "require sponsor"], "No")
    answer_question(
        page,
        ["available to begin", "available to start", "able to start", "when can you start"],
        "Immediately",
        fallbacks=["1 week", "2 weeks", "Two weeks", "Yes"],
    )
    answer_question(page, ["consent to receive", "text messages", "sms"], "Yes")
    answer_question(
        page,
        ["resident of", "country of residence", "country you reside", "where do you live", "country"],
        country,
        fallbacks=["No"],
    )


def answer_question(page, keywords, desired_value: str, fallbacks=None) -> bool:
    """Locate a form control whose label contains any of `keywords` and answer.

    Works with both native <select> and ARIA combo-boxes that use
    `aria-labelledby` (Greenhouse pattern) or `<label for=…>` (Lever, Ashby).
    """
    candidates = [desired_value] + list(fallbacks or [])
    for kw in keywords:
        try:
            ctrl = page.get_by_label(kw, exact=False).first
            if ctrl.count() == 0:
                continue
        except Exception:
            continue
        try:
            tag = (ctrl.evaluate("e => e.tagName.toLowerCase()") or "")
        except Exception:
            tag = ""
        try:
            role = (ctrl.get_attribute("role") or "").lower()
        except Exception:
            role = ""

        for value in candidates:
            if tag == "select":
                if select_native(ctrl, value):
                    return True
            elif role == "combobox" or tag in ("input", "button"):
                if select_combobox(page, ctrl, value):
                    return True
    return False


def select_native(locator, desired_value: str) -> bool:
    """Try native <select>: by label, then value (mixed-case + lower), then index 1."""
    for strategy in (
        lambda: locator.select_option(label=desired_value),
        lambda: locator.select_option(value=desired_value),
        lambda: locator.select_option(value=desired_value.lower()),
        lambda: locator.select_option(index=1),
    ):
        try:
            strategy()
            return True
        except Exception:
            continue
    return False


# Selectors that match the *visible* open select menu for various ATSes.
# Order matters — most-specific first. The phone-country picker on Greenhouse
# keeps a hidden listbox in the DOM permanently, so we MUST scope option
# queries to the open menu container.
_OPEN_MENU_SELECTORS = (
    ".select__menu, [class*='select__menu-list'], "                          # Greenhouse react-select
    "div[role='listbox']:visible, ul[role='listbox']:visible, "              # generic ARIA
    "[class*='_dropdown_'], [class*='menu-list'], [class*='Dropdown']"      # Ashby / Lever variants
)


def select_combobox(page, trigger, desired_value: str) -> bool:
    """Open an ARIA / react-select combo-box and CLICK the matching option.

    No-type policy: typing into the input leaves garbage instead of a
    committed selection on react-select. If no option matches we return False
    and leave the field empty for Gemini / the user.
    """
    import time as _t

    def _committed_text() -> str:
        try:
            return (trigger.evaluate("""el => {
                let root = el.closest('[class*=\"value-container\"]')
                        || el.closest('[class*=\"select__control\"]')
                        || el.closest('[class*=\"select-shell\"]')
                        || el.closest('[class*=\"select__container\"]')
                        || el.closest('[class*=\"_select_\"]')
                        || el.closest('[class*=\"_combobox_\"]');
                if (!root) {
                    let p = el.parentElement;
                    for (let i=0; i<6 && p; i++, p = p.parentElement) {
                        if (p.querySelector('[class*=\"single-value\"], [class*=\"singleValue\"]')) {
                            root = p; break;
                        }
                    }
                }
                if (!root) return '';
                const sv = root.querySelector('[class*=\"single-value\"], [class*=\"singleValue\"]');
                if (sv) return (sv.innerText || '').trim();
                // Ashby/Lever may not use single-value; check for any sibling
                // div with text matching the control text.
                return '';
            }""") or "").strip()
        except Exception:
            return ""

    def _open_listbox() -> bool:
        try:
            trigger.scroll_into_view_if_needed()
            trigger.focus()
            page.keyboard.press("ArrowDown")
            page.wait_for_selector(_OPEN_MENU_SELECTORS, timeout=1_500)
            return True
        except Exception:
            pass
        try:
            ctrl = trigger.locator(
                "xpath=ancestor::div["
                "contains(@class,'select__control') or "
                "contains(@class,'select-shell') or "
                "contains(@class,'value-container') or "
                "contains(@class,'_select_') or "
                "contains(@class,'_combobox_')][1]"
            )
            if ctrl.count() > 0:
                ctrl.first.click()
                page.wait_for_selector(_OPEN_MENU_SELECTORS, timeout=1_500)
                return True
        except Exception:
            pass
        try:
            trigger.click(force=True)
            page.wait_for_selector(_OPEN_MENU_SELECTORS, timeout=1_500)
            return True
        except Exception:
            return False

    if not _open_listbox():
        try: page.keyboard.press("Escape")
        except Exception: pass
        return False

    # Enumerate visible options inside the open menu only.
    try:
        options = page.evaluate("""() => {
            const menus = [...document.querySelectorAll(
                '.select__menu, [class*=\"select__menu-list\"], [role=listbox], '
                + '[class*=\"_dropdown_\"], [class*=\"menu-list\"], [class*=\"Dropdown\"]'
            )].filter(m => m.offsetParent !== null);
            const seen = new Set();
            const out = [];
            for (const m of menus) {
                for (const o of m.querySelectorAll('[role=option]')) {
                    const t = (o.innerText || '').trim();
                    if (t && !seen.has(t)) { seen.add(t); out.push(t); }
                }
            }
            return out;
        }""") or []
    except Exception:
        options = []

    if not options:
        try: page.keyboard.press("Escape")
        except Exception: pass
        return False

    desired_lower = (desired_value or "").lower().strip()
    pick = None
    for o in options:
        if o.lower() == desired_lower: pick = o; break
    if pick is None:
        for o in options:
            if o.lower().startswith(desired_lower): pick = o; break
    if pick is None:
        for o in options:
            if desired_lower in o.lower(): pick = o; break

    if pick is None:
        try: page.keyboard.press("Escape")
        except Exception: pass
        return False

    try:
        opt = page.locator(
            ".select__menu [role=option], "
            "[class*='select__menu-list'] [role=option], "
            "[class*='_dropdown_'] [role=option], "
            "[role=listbox]:visible [role=option]"
        ).filter(has_text=pick).first
        if opt.count() == 0:
            try: page.keyboard.press("Escape")
            except Exception: pass
            return False
        opt.scroll_into_view_if_needed()
        opt.click()
        _t.sleep(0.2)
    except Exception:
        try: page.keyboard.press("Escape")
        except Exception: pass
        return False

    # Some non-react-select widgets don't expose a single-value div; if the
    # menu is now closed we treat the click as committed.
    if _committed_text():
        return True
    try:
        menus_open = page.locator(_OPEN_MENU_SELECTORS).count()
        return menus_open == 0
    except Exception:
        return True


def fill_other_email_inputs(page, email: str):
    """Fill any empty extra `input[type=email]` (confirm-email, second email)."""
    if not email:
        return
    try:
        inputs = page.locator("input[type='email']")
        for i in range(inputs.count()):
            el = inputs.nth(i)
            try:
                if (el.input_value() or "").strip():
                    continue
                el.fill(email)
            except Exception:
                continue
    except Exception:
        pass


def tick_required_consent_checkboxes(page):
    """Tick all required `<input type=checkbox>` using Playwright's trusted click.

    React-controlled checkboxes ignore both `el.checked = true` (skips React's
    onChange tracker) and JS `.click()` (synthetic, sometimes filtered).
    Playwright's `locator.click()` dispatches a real trusted mouse event that
    React processes — the box visibly toggles and form state stays in sync.
    """
    try:
        ids = page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('input[type=checkbox]')) {
                const req = el.required || el.getAttribute('aria-required') === 'true';
                if (req && !el.checked && el.id) out.push(el.id);
            }
            return out;
        }""") or []
    except Exception:
        ids = []

    for cid in ids:
        # 1. Click the associated label after scrolling it into view
        try:
            lbl = page.locator(f"label[for='{cid}']")
            if lbl.count() > 0:
                lbl.first.scroll_into_view_if_needed()
                lbl.first.click()
                if page.locator(f"#{cid}").is_checked():
                    continue
        except Exception:
            pass
        # 2. Force-check the input itself
        try:
            box = page.locator(f"#{cid}")
            box.scroll_into_view_if_needed()
            box.check(force=True)
            if box.is_checked():
                continue
        except Exception:
            pass
        # 3. JS fallback — at least the form state is correct even if visually off
        try:
            page.evaluate(
                """(id) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    const lbl = document.querySelector(`label[for='${id}']`);
                    if (lbl) lbl.click();
                    if (!el.checked) {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
                cid,
            )
        except Exception:
            pass


# ── Coverage + Gemini-driven unknown-question answering ────────────────────

def compute_prefill_coverage(page) -> Dict:
    """Return {required, filled, pct, empty_labels} for visible required fields."""
    try:
        data = page.evaluate("""() => {
            const out = {required: 0, filled: 0, empty_labels: []};
            const fields = document.querySelectorAll('input, select, textarea');
            for (const el of fields) {
                if (['hidden','submit','button'].includes(el.type)) continue;
                const required = el.required || el.getAttribute('aria-required') === 'true';
                if (!required) continue;
                out.required += 1;
                let filled = false;
                if (el.type === 'checkbox') {
                    filled = el.checked;
                } else if ((el.getAttribute('role') || '') === 'combobox') {
                    // react-select-style: visible single-value sibling
                    let txt = '';
                    let root = el.closest('[class*="value-container"]')
                            || el.closest('[class*="select__control"]')
                            || el.closest('[class*="select-shell"]')
                            || el.closest('[class*="select__container"]')
                            || el.closest('[class*="_select_"]');
                    if (!root) {
                        let p = el.parentElement;
                        for (let i=0; i<6 && p; i++, p = p.parentElement) {
                            if (p.querySelector('[class*="single-value"], [class*="singleValue"]')) {
                                root = p; break;
                            }
                        }
                    }
                    if (root) {
                        const sv = root.querySelector('[class*="single-value"], [class*="singleValue"]');
                        if (sv) txt = (sv.innerText || '').trim();
                    }
                    filled = !!(txt || (el.value || '').trim());
                } else {
                    filled = (el.value || '').trim().length > 0;
                }
                if (filled) {
                    out.filled += 1;
                } else {
                    let lbl = '';
                    if (el.id) {
                        const f = document.querySelector(`label[for='${el.id}']`);
                        if (f) lbl = f.innerText.trim();
                    }
                    if (!lbl && el.getAttribute('aria-labelledby')) {
                        const ref = document.getElementById(el.getAttribute('aria-labelledby'));
                        if (ref) lbl = ref.innerText.trim();
                    }
                    if (!lbl) lbl = el.name || el.id || '(no label)';
                    out.empty_labels.push(lbl.replace(/\\*$/, '').slice(0, 80));
                }
            }
            return out;
        }""") or {"required": 0, "filled": 0, "empty_labels": []}
    except Exception:
        data = {"required": 0, "filled": 0, "empty_labels": []}
    req = max(data.get("required", 0), 0)
    fil = data.get("filled", 0)
    pct = int(round((fil / req) * 100)) if req else 100
    data["pct"] = pct
    return data


def list_remaining_unanswered(page) -> List[Dict]:
    """Return [{kind, id, name, label}] for required fields still empty."""
    try:
        return page.evaluate("""() => {
            const fields = [];
            for (const el of document.querySelectorAll('input, select, textarea')) {
                if (['hidden','submit','button'].includes(el.type)) continue;
                const required = el.required || el.getAttribute('aria-required') === 'true';
                if (!required) continue;
                const filled = el.type === 'checkbox' ? el.checked : (el.value || '').trim().length > 0;
                if (filled) continue;
                let label = '';
                if (el.id) {
                    const f = document.querySelector(`label[for='${el.id}']`);
                    if (f) label = f.innerText.trim();
                }
                if (!label && el.getAttribute('aria-labelledby')) {
                    const ref = document.getElementById(el.getAttribute('aria-labelledby'));
                    if (ref) label = ref.innerText.trim();
                }
                if (!label) label = el.name || el.id || '';
                label = label.replace(/\\*$/, '').trim();
                const role = (el.getAttribute('role') || '').toLowerCase();
                let kind = 'text';
                if (el.tagName.toLowerCase() === 'select') kind = 'select';
                else if (role === 'combobox') kind = 'combobox';
                else if (el.tagName.toLowerCase() === 'textarea') kind = 'textarea';
                fields.push({kind, id: el.id, name: el.name, label});
            }
            return fields;
        }""") or []
    except Exception:
        return []


def enumerate_combobox_options(page, field_id: str) -> List[str]:
    """Open a combo-box by id and read its visible option strings."""
    try:
        el = page.locator(f"#{field_id}")
        el.scroll_into_view_if_needed()
        el.focus()
        page.keyboard.press("ArrowDown")
        page.wait_for_selector(_OPEN_MENU_SELECTORS, timeout=1_500)
        opts = page.evaluate("""() => {
            const menus = [...document.querySelectorAll(
                '.select__menu, [class*=\"select__menu-list\"], [role=listbox], '
                + '[class*=\"_dropdown_\"], [class*=\"menu-list\"], [class*=\"Dropdown\"]'
            )].filter(m => m.offsetParent !== null);
            const out = [];
            for (const m of menus) {
                for (const o of m.querySelectorAll('[role=option]')) {
                    const t = (o.innerText || '').trim();
                    if (t) out.push(t);
                }
            }
            return out;
        }""") or []
        try: page.keyboard.press("Escape")
        except Exception: pass
        return opts
    except Exception:
        try: page.keyboard.press("Escape")
        except Exception: pass
        return []


def _gemini_answer(question: str, options: list, resume_text: str, profile: Dict) -> str:
    """Ask Gemini for the best answer to a form question. Returns '' on failure."""
    import os
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return ""
    profile_summary = (
        f"Name: {profile.get('full_name','')}, Email: {profile.get('email','')}, "
        f"Location: {profile.get('location','India')}, "
        f"Country: {profile.get('country','India')}, "
        f"LinkedIn: {profile.get('linkedin_url','')}, GitHub: {profile.get('github_url','')}."
    )
    if options:
        opts_str = "\n".join(f"  - {o}" for o in options[:60])
        prompt = (
            f"You are filling a job application form for the candidate.\n\n"
            f"Candidate profile: {profile_summary}\n"
            f"Resume excerpt:\n{(resume_text or '')[:1500]}\n\n"
            f"Question on the form: \"{question}\"\n"
            f"Available options:\n{opts_str}\n\n"
            f"Pick the single option that best fits this candidate based on "
            f"the resume and profile. Reply with ONLY the exact option text. "
            f"If you cannot determine a confident answer from the data above, "
            f"reply with the single word: SKIP. Do NOT guess randomly."
        )
    else:
        prompt = (
            f"You are filling a job application form for the candidate.\n\n"
            f"Candidate profile: {profile_summary}\n"
            f"Resume excerpt:\n{(resume_text or '')[:1500]}\n\n"
            f"Question on the form: \"{question}\"\n\n"
            f"Provide a concise honest answer in 1–2 short sentences. "
            f"Plain text only, no markdown. If you cannot answer from the "
            f"data above, reply with the single word: SKIP."
        )
    try:
        import httpx
        from job_scout.ai.gemini import GEMINI_API_URL
        resp = httpx.Client(timeout=15.0).post(
            f"{GEMINI_API_URL}?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 120, "temperature": 0.2},
            },
        )
        if resp.status_code != 200:
            return ""
        cands = resp.json().get("candidates", [])
        if not cands:
            return ""
        parts = cands[0].get("content", {}).get("parts", [])
        if not parts:
            return ""
        answer = (parts[0].get("text", "") or "").strip().strip('"').strip("'")
        if answer.upper() == "SKIP":
            return ""
        return answer
    except Exception:
        return ""


def answer_unknowns_with_gemini(page, resume_text: str, profile: Dict) -> List[str]:
    """For each remaining unanswered required field, ask Gemini and apply.

    Returns a list of "label → answer" strings for audit notes.
    """
    notes = []
    fields = list_remaining_unanswered(page)
    for f in fields:
        label = (f.get("label") or "").strip()
        if not label:
            continue
        skip_kw = ("first name", "last name", "email", "phone", "country code")
        if any(k in label.lower() for k in skip_kw):
            continue
        if f["kind"] in ("combobox", "select"):
            options = []
            if f["kind"] == "combobox":
                options = enumerate_combobox_options(page, f.get("id", ""))
            elif f["kind"] == "select":
                try:
                    options = page.locator(f"#{f['id']} option").all_text_contents() or []
                except Exception:
                    options = []
            answer = _gemini_answer(label, options, resume_text, profile)
            if not answer:
                continue
            try:
                ctrl = page.locator(f"#{f['id']}")
                if f["kind"] == "select":
                    if select_native(ctrl, answer):
                        notes.append(f"{label[:40]} → {answer[:40]}")
                else:
                    if select_combobox(page, ctrl, answer):
                        notes.append(f"{label[:40]} → {answer[:40]}")
            except Exception:
                continue
        else:
            answer = _gemini_answer(label, [], resume_text, profile)
            if not answer:
                continue
            try:
                page.locator(f"#{f['id']}").fill(answer[:500])
                notes.append(f"{label[:40]} → {answer[:60]}")
            except Exception:
                continue
    return notes


def build_prefill_notes(coverage: Dict, ai_notes: List[str]) -> str:
    """Format the coverage + AI summary into a single notes string."""
    parts = [f"Prefilled {coverage['filled']}/{coverage['required']} required fields ({coverage['pct']}%)."]
    empties = coverage.get("empty_labels") or []
    if empties:
        parts.append("Still empty: " + "; ".join(empties[:5]))
    if ai_notes:
        parts.append("Gemini answers: " + "; ".join(ai_notes[:5]))
    return " ".join(parts)
