/*
 * class-filter.js — Φιλτράρισμα μενού ανά τάξη
 *
 * Όταν ο μαθητής βρίσκεται μέσα σε μια τάξη (π.χ. /docs/gymnasio-a/...),
 * το πλαϊνό μενού δείχνει ΜΟΝΟ τα μαθήματα αυτής της τάξης. Επιπλέον
 * προστίθεται ένα αναπτυσσόμενο «Αλλαγή τάξης» πάνω από το μενού.
 */
(function () {
  'use strict';

  var CLASSES = [
    { slug: 'gymnasio-a', label: "Α' Γυμνασίου", group: 'Γυμνάσιο' },
    { slug: 'gymnasio-b', label: "Β' Γυμνασίου", group: 'Γυμνάσιο' },
    { slug: 'gymnasio-g', label: "Γ' Γυμνασίου", group: 'Γυμνάσιο' },
    { slug: 'lykeio-a',   label: "Α' Λυκείου",   group: 'Λύκειο' },
    { slug: 'lykeio-b',   label: "Β' Λυκείου",   group: 'Λύκειο' },
    { slug: 'lykeio-g',   label: "Γ' Λυκείου",   group: 'Λύκειο' }
  ];

  /** Βρίσκει τη βάση του site (π.χ. "/docs/") από το τρέχον URL. */
  function siteBase() {
    var path = window.location.pathname;
    var idx = path.indexOf('/docs/');
    if (idx !== -1) return path.slice(0, idx + '/docs/'.length);
    return '/docs/';
  }

  /** Επιστρέφει το slug της τάξης στον τρέχον δρόμο ή null. */
  function currentClass() {
    var path = window.location.pathname;
    for (var i = 0; i < CLASSES.length; i++) {
      if (path.indexOf('/' + CLASSES[i].slug + '/') !== -1) return CLASSES[i].slug;
    }
    return null;
  }

  /** Επιστρέφει το slug τάξης από ένα href αλλιώς null. */
  function classOfHref(href) {
    if (!href) return null;
    for (var i = 0; i < CLASSES.length; i++) {
      if (href.indexOf('/' + CLASSES[i].slug + '/') !== -1 ||
          href.indexOf(CLASSES[i].slug + '/') === 0) return CLASSES[i].slug;
    }
    return null;
  }

  /** Κρύβει τα στοιχεία μενού άλλων τάξεων. */
  function filterNav(slug) {
    var nav = document.querySelector('.md-sidebar--primary nav.md-nav--primary');
    if (!nav) return;

    // Κάθε κορυφαίο στοιχείο της λίστας πλοήγησης
    var items = nav.querySelectorAll(':scope > ul.md-nav__list > li.md-nav__item');
    items.forEach(function (li) {
      var links = li.querySelectorAll('a.md-nav__link');
      var classesFound = {};
      links.forEach(function (a) {
        var c = classOfHref(a.getAttribute('href'));
        if (c) classesFound[c] = true;
      });
      var keys = Object.keys(classesFound);
      // Αν το μπλοκ αφορά αποκλειστικά άλλες τάξεις -> κρύψε το
      if (keys.length > 0 && keys.indexOf(slug) === -1) {
        li.style.display = 'none';
        li.setAttribute('data-class-filtered', 'true');
      } else {
        li.style.display = '';
        li.removeAttribute('data-class-filtered');
      }
    });

    // Μέσα στο εναπομείναν μπλοκ, κρύψε υπο-ενότητες άλλων τάξεων
    nav.querySelectorAll('li.md-nav__item--nested').forEach(function (li) {
      if (li.getAttribute('data-class-filtered') === 'true') return;
      var own = li.querySelector(':scope > a.md-nav__link, :scope > label.md-nav__link');
      var subLinks = li.querySelectorAll('ul.md-nav__list a.md-nav__link');
      var found = {};
      subLinks.forEach(function (a) {
        var c = classOfHref(a.getAttribute('href'));
        if (c) found[c] = true;
      });
      var ks = Object.keys(found);
      if (ks.length > 0 && ks.indexOf(slug) === -1) {
        li.style.display = 'none';
      } else {
        li.style.display = '';
      }
    });
  }

  /** Δημιουργεί το αναπτυσσόμενο επιλογής τάξης. */
  function buildSwitcher(slug) {
    var nav = document.querySelector('.md-sidebar--primary nav.md-nav--primary');
    if (!nav || nav.querySelector('.class-switcher')) return;

    var box = document.createElement('div');
    box.className = 'class-switcher';

    var label = document.createElement('label');
    label.className = 'class-switcher__label';
    label.textContent = 'Τάξη';
    label.setAttribute('for', 'class-switcher-select');

    var select = document.createElement('select');
    select.id = 'class-switcher-select';
    select.className = 'class-switcher__select';

    var base = siteBase();
    var optAll = document.createElement('option');
    optAll.value = base;
    optAll.textContent = '— Όλες οι τάξεις —';
    select.appendChild(optAll);

    ['Γυμνάσιο', 'Λύκειο'].forEach(function (group) {
      var og = document.createElement('optgroup');
      og.label = group;
      CLASSES.filter(function (c) { return c.group === group; }).forEach(function (c) {
        var o = document.createElement('option');
        o.value = base + c.slug + '/';
        o.textContent = c.label;
        if (c.slug === slug) o.selected = true;
        og.appendChild(o);
      });
      select.appendChild(og);
    });

    select.addEventListener('change', function () {
      window.location.href = select.value;
    });

    box.appendChild(label);
    box.appendChild(select);
    nav.insertBefore(box, nav.firstChild);
  }

  function apply() {
    var slug = currentClass();
    buildSwitcher(slug);
    if (slug) {
      filterNav(slug);
      document.body.setAttribute('data-class', slug);
    } else {
      document.body.removeAttribute('data-class');
      // Επαναφορά εμφάνισης όταν δεν είμαστε σε τάξη
      document.querySelectorAll('[data-class-filtered="true"]').forEach(function (el) {
        el.style.display = '';
        el.removeAttribute('data-class-filtered');
      });
    }
  }

  // Αρχική εφαρμογή + υποστήριξη instant navigation του Material
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(apply);
  }
})();