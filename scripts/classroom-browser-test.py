#!/opt/school-portal/venv/bin/python
"""
classroom-browser-test.py — Έλεγχος της Ζωντανής Τάξης σε ΠΡΑΓΜΑΤΙΚΟ browser.

Headless Chromium (CDP, ίδιο μοτίβο με το browser-test.py): είσοδος guest με
παιχνιδιάρικο όνομα, μόνιμο μενού ανά ρόλο, άνοιγμα εφαρμογής σε iframe μέσα
στο κεντρικό παράθυρο, dock⇄float εργαλειοθήκες, είσοδος καθηγητή & αποστολή
ανακοίνωσης που εμφανίζεται ζωντανά στον guest. Εκτέλεση:
    /opt/school-portal/venv/bin/python scripts/classroom-browser-test.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import (TEACHER_CODE, check, launch_chrome, new_tab, results,
                 stop_chrome, wait_for)

PORT = 9345
BASE = "http://127.0.0.1"


def alpine(cdp):
    """Πρόσβαση στο Alpine component του shell."""
    return "document.querySelector('body')._x_dataStack[0]"



def main() -> int:
    try:
        proc, guest = launch_chrome(PORT, timeout=60)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    cdps = [guest]
    try:
        guest.send("Page.enable"); guest.send("Runtime.enable")

        print("\n=== 1. Είσοδος guest & παιχνιδιάρικο όνομα ===")
        guest.send("Page.navigate", {"url": f"{BASE}/classroom/"})
        ok = wait_for(guest, f"!!({alpine(guest)}) && !!window.Alpine", timeout=30)
        check("Το shell φορτώνει (Alpine)", bool(ok))
        guest.evaluate(f"{alpine(guest)}.joinRole='guest'; {alpine(guest)}.join()")
        ident = wait_for(guest, f"{alpine(guest)}.identity && {alpine(guest)}.identity.name", timeout=15)
        check("Guest όνομα τύπου Google Docs", bool(ident and " " in str(ident)), str(ident))
        ok = wait_for(guest, f"{alpine(guest)}.wsOk === true", timeout=15)
        check("WebSocket συνδέθηκε (heartbeat)", bool(ok))
        menu = guest.evaluate(f"{alpine(guest)}.menu.map(m=>m.id)")
        check("Μενού guest: χωρίς Forum", "forum" not in menu and "mathimata" in menu, str(menu))

        print("\n=== 2. Εφαρμογή σε iframe ΜΕ μόνιμο μενού ===")
        guest.evaluate(f"{alpine(guest)}.openMenu({alpine(guest)}.menu.find(m=>m.url==='/docs/'))")
        ok = wait_for(guest, "document.getElementById('app-frame') && document.getElementById('app-frame').src.includes('/docs/')")
        check("Το /docs/ ανοίγει σε iframe", bool(ok))
        header_visible = guest.evaluate(
            "(()=>{const h=document.querySelector('header');const r=h.getBoundingClientRect();"
            "return r.height>0 && getComputedStyle(h).display!=='none'})()")
        check("Το κεντρικό μενού παραμένει ορατό", bool(header_visible))
        loaded = wait_for(guest,
            "(()=>{try{const d=document.getElementById('app-frame').contentDocument;"
            "return d && d.readyState==='complete' && d.body && d.body.innerHTML.length>500}catch(e){return false}})()",
            timeout=30)
        check("Το iframe φορτώνει πραγματικό περιεχόμενο (same-origin)", bool(loaded))

        print("\n=== 3. Εργαλειοθήκες dock ⇄ float ===")
        try:  # καθαρισμός τυχόν αποθηκευμένων θέσεων από προηγούμενη εκτέλεση
            guest.evaluate("localStorage.removeItem('classroom.panels')")
            guest.evaluate(f"{alpine(guest)}.loadConfig()")
            time.sleep(1.0)
        except Exception:
            pass
        panels = guest.evaluate(f"{alpine(guest)}.panels.map(p=>({{id:p.id,mode:p.mode}}))")
        check("Ο guest έχει εργαλειοθήκες από το config", len(panels) >= 1, str(panels))
        di = guest.evaluate(f"{alpine(guest)}.panels.findIndex(p=>p.mode==='dock')")
        dock_id = guest.evaluate(f"{alpine(guest)}.panels[{di}].id")
        # Περιεχόμενο widget ΠΡΙΝ το float (π.χ. chat input ή timer placeholder)
        before = guest.evaluate(
            f"(()=>{{const s=document.getElementById('dock-slot-{dock_id}');"
            "return s ? s.innerHTML.length : -1})()")
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.toggleMode(a.panels[{di}])}})()")
        time.sleep(0.8)
        mode = guest.evaluate(f"{alpine(guest)}.panels[{di}].mode")
        floated = guest.evaluate("!!document.querySelector('.tb-panel')")
        check("Ξεκούμπωμα → πλωτή εργαλειοθήκη (float)", mode == "float" and floated, mode)
        # BUG FIX: το widget πρέπει να μετακομίσει στο float slot με τα περιεχόμενά του
        after = guest.evaluate(
            f"(()=>{{const s=document.getElementById('float-slot-{dock_id}');"
            "if(!s) return -1; const w=s.querySelector('[data-widget]');"
            "return w ? w.innerHTML.length : 0})()")
        check(f"Το float διατηρεί τα περιεχόμενα του widget '{dock_id}'",
              isinstance(after, int) and after > 50 and after >= (before or 0) * 0.8,
              f"before={before} after={after}")
        visible = guest.evaluate(
            f"(()=>{{const el=document.getElementById('float-{dock_id}');"
            "if(!el) return false; const r=el.getBoundingClientRect();"
            "return r.width>100 && r.height>60 && getComputedStyle(el).display!=='none'})()")
        check("Η πλωτή εργαλειοθήκη είναι ορατή με σώμα", bool(visible))
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.panels[{di}].x=300;a.panels[{di}].y=200}})()")
        time.sleep(0.5)
        pos = guest.evaluate(f"(()=>{{const a={alpine(guest)};const el=document.getElementById('float-'+a.panels[{di}].id);if(!el)return null;const r=el.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]}})()")
        check("Η πλωτή εργαλειοθήκη τοποθετείται ελεύθερα", pos == [300, 200], str(pos))
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.toggleMode(a.panels[{di}])}})()")
        time.sleep(0.5)
        check("Ξανακούμπωμα → dock", guest.evaluate(f"{alpine(guest)}.panels[{di}].mode") == "dock")


        print("\n=== 4. Καθηγητής σε 2η καρτέλα: roster & ανακοίνωση ζωντανά ===")
        teacher = new_tab(PORT, f"{BASE}/classroom/", timeout=60)
        cdps.append(teacher)
        teacher.send("Page.enable"); teacher.send("Runtime.enable")
        wait_for(teacher, f"!!({alpine(teacher)})", timeout=30)
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.joinRole='teacher';a.joinCode='{TEACHER_CODE}';a.joinName='Καθηγητής UI';a.join()}})()")
        ok = wait_for(teacher, f"{alpine(teacher)}.role==='teacher' && {alpine(teacher)}.wsOk", timeout=15)
        check("Είσοδος καθηγητή από το UI", bool(ok))
        roster_ok = wait_for(teacher, f"{alpine(teacher)}.roster.some(c=>c.role==='guest')", timeout=15)
        check("Ο καθηγητής βλέπει τον guest στο roster", bool(roster_ok))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.cmd.text='Καλημέρα από το UI test!';a.cmd.audience='all';a.sendAnnounce('announce')}})()")
        toast = wait_for(guest, f"{alpine(guest)}.toasts.some(t=>t.text.includes('Καλημέρα από το UI test'))", timeout=15)
        check("Ο guest βλέπει την ανακοίνωση ζωντανά (toast)", bool(toast))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.cmd.timerLabel='UI Timer';a.cmd.timerMin=1;a.cmd.timerVis='public';a.sendTimer()}})()")
        timer_ok = wait_for(guest, f"{alpine(guest)}.activeTimers.some(t=>t.label==='UI Timer')", timeout=15)
        check("Δημόσιος timer εμφανίζεται στον guest", bool(timer_ok))
        countdown = guest.evaluate(f"(()=>{{const a={alpine(guest)};const t=a.activeTimers.find(x=>x.label==='UI Timer');return a.fmtLeft(a.timerLeft(t))}})()")
        check("Αντίστροφη μέτρηση σε μορφή mm:ss", bool(countdown and ":" in str(countdown)), str(countdown))
        # BUG FIX: ο guest μπορεί πλέον να κλείσει (τοπικά) το παράθυρο του timer
        guest.evaluate(f"(()=>{{const a={alpine(guest)};const t=a.activeTimers.find(x=>x.label==='UI Timer');a.dismissTimer(t)}})()")
        time.sleep(0.4)
        gone = guest.evaluate(f"!{alpine(guest)}.activeTimers.some(t=>t.label==='UI Timer')")
        check("Ο guest κλείνει το timer με το ✕ (τοπική απόκρυψη)", bool(gone))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};const t=a.activeTimers.find(x=>x.label==='UI Timer');if(t)a.stopTimer(t.id)}})()")
        time.sleep(0.4)

        print("\n=== 5. Poll: ψήφος → auto-close → reconnect ΔΕΝ ξαναδείχνει modal ===")
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.cmd.audience='guests';a.cmd.pollQ='UI poll: όλα καλά;';a.cmd.pollOpts='Ναι, Όχι';a.cmd.pollShow=true;a.cmd.pollAuto=true;a.sendPoll()}})()")
        poll_shown = wait_for(guest, f"{alpine(guest)}.activePoll && {alpine(guest)}.activePoll.question.includes('UI poll')", timeout=15)
        check("Ο guest βλέπει το poll modal", bool(poll_shown))
        guest.evaluate(f"{alpine(guest)}.votePoll(0)")
        closed = wait_for(guest, f"{alpine(guest)}.activePoll && {alpine(guest)}.activePoll.closed === true", timeout=15)
        check("Auto-close: το poll ολοκληρώθηκε όταν ψήφισαν όλοι", bool(closed))
        results_visible = guest.evaluate(f"!!{alpine(guest)}.pollResults && {alpine(guest)}.pollResults.total >= 1")
        check("Ο guest βλέπει τα τελικά αποτελέσματα στο κλειστό poll", bool(results_visible))
        guest.evaluate(f"{alpine(guest)}.hidePoll()")
        # reconnect: προσομοίωση με νέο WS — το welcome δεν πρέπει να φέρει το poll
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.ws.close()}})()")
        back = wait_for(guest, f"{alpine(guest)}.wsOk === true", timeout=20)
        time.sleep(1.0)
        no_reshow = guest.evaluate(f"!{alpine(guest)}.activePoll")
        check("Reconnect: το απαντημένο poll ΔΕΝ επανεμφανίζεται", bool(back and no_reshow))

        print("\n=== 6. Κονσόλα διαχείρισης & σύνθετη ανακοίνωση (UI καθηγητή) ===")
        has_manage = teacher.evaluate(f"{alpine(teacher)}.menu.some(m=>m.url==='#manage')")
        check("Μενού καθηγητή: 🗄️ Διαχείριση", bool(has_manage))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.openMenu(a.menu.find(m=>m.url==='#manage'))}})()")
        mg_ok = wait_for(teacher, "!!document.getElementById('mg-body') && document.querySelectorAll('#mg-body .mg-check').length >= 1", timeout=15)
        check("Η κονσόλα φορτώνει λίστα με checkboxes (bulk)", bool(mg_ok))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.manageTab='polls';a.renderManage(document.getElementById('panel-host'))}})()")
        polls_tab = wait_for(teacher, f"{alpine(teacher)}.mgPolls.length >= 1", timeout=15)
        check("Καρτέλα Δημοσκοπήσεις: αποθηκευμένα polls με αποτελέσματα", bool(polls_tab))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.toggleAdvMode()}})()")
        cat_ok = wait_for(teacher, f"{alpine(teacher)}.catalog.lessons.length >= 3", timeout=15)
        check("Σύνθετη ανακοίνωση: κατάλογος μαθημάτων φορτώνει", bool(cat_ok))
        fav_filter = teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.linkFilter.fav=true;const n=a.filteredCatalog().length;a.linkFilter.fav=false;return n}})()")
        check("Φίλτρο ⭐ αγαπημένων λειτουργεί", isinstance(fav_filter, int) and fav_filter >= 1, str(fav_filter))

        r = results()
        print(f"\n{'✓ ΟΛΟΙ οι browser έλεγχοι πέρασαν' if not r.failed else '✗ ΑΠΟΤΥΧΙΑ'} ({r.passed} ✓ / {r.failed} ✗)")
        return r.exit_code()
    finally:
        for c in cdps:
            c.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
