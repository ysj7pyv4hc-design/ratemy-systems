/* ============================================================
   Rate My Systems — public signal view (signal.js)
   ZERO-BS + A1: no leaderboards. Global picture + look up one
   workplace vs. the expected range. Never a ranked list.
   ============================================================ */
(function () {
  'use strict';

  var PILLAR_LABEL = { inputs: 'Inputs', environment: 'Environment', governance: 'Governance', feedback: 'Feedback' };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return (s == null ? '' : String(s))
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function r1(n) { return n == null ? '—' : (Math.round(n * 10) / 10).toFixed(1); }

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    $('toast-root').appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }

  async function api(path) {
    var res = await fetch(path, { credentials: 'same-origin' });
    var data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Request failed');
    return data;
  }

  function bar(label, value) {
    var pct = value == null ? 0 : (value / 5) * 100;
    return '<div class="bar-row"><div class="bar-head"><span>' + esc(label) + '</span>' +
      '<span class="val">' + r1(value) + '</span></div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div></div>';
  }

  /* ---------- global ---------- */
  async function loadGlobal() {
    try {
      var d = await api('/v1/scores/global');
      var labels = d.category_labels || {};
      if (!d.published || !d.n_raters) {
        $('overall-count').textContent = '0 ratings published yet — be the first';
        return;
      }
      var s = d.scores;
      $('overall-count').textContent = d.n_raters + ' raters · index ' + (s.index == null ? '—' : s.index) + ' / 100';

      var html = '';
      if (s.strength && s.gap) {
        html += '<div class="bar-head"><span class="amber">Strongest system overall</span></div>';
        html += bar(labels[s.strength] || s.strength, s.categories[s.strength]);
        html += '<div class="bar-head"><span>Biggest gap overall</span></div>';
        html += bar(labels[s.gap] || s.gap, s.categories[s.gap]);
      }
      html += '<div class="spacer"></div>';
      Object.keys(PILLAR_LABEL).forEach(function (p) {
        html += bar(PILLAR_LABEL[p], s.pillars[p]);
      });
      var ctx = s.control_context || {};
      if (ctx.expected_low != null) {
        html += '<p class="small muted">Expected range across ' + ctx.n_companies +
          ' rated workplaces: ' + ctx.expected_low + '–' + ctx.expected_high +
          ' (index). Workplaces are compared to this range — never ranked.</p>';
      }
      $('overall-bars').innerHTML = html;
    } catch (e) { toast(e.message); }
  }

  /* ---------- one workplace lookup (never a list of scores) ---------- */
  var searchTimer = null;
  $('filter').addEventListener('input', function () {
    clearTimeout(searchTimer);
    var q = this.value.trim();
    if (q.length < 2) { $('companies').innerHTML = ''; return; }
    searchTimer = setTimeout(function () { searchCompanies(q); }, 250);
  });

  async function searchCompanies(q) {
    try {
      var d = await api('/v1/companies?q=' + encodeURIComponent(q));
      var html = '<ul class="results">';
      d.companies.forEach(function (c) {
        html += '<li><button type="button" data-id="' + esc(c.id) + '">' + esc(c.name) + '</button></li>';
      });
      html += '</ul><div id="company-detail"></div>';
      $('companies').innerHTML = html;
      Array.prototype.forEach.call($('companies').querySelectorAll('button'), function (btn) {
        btn.addEventListener('click', function () { loadCompany(this.dataset.id); });
      });
    } catch (e) { toast(e.message); }
  }

  async function loadCompany(id) {
    try {
      var d = await api('/v1/scores/company/' + encodeURIComponent(id));
      var el = $('company-detail');
      var html = '<div class="card stack"><h3>' + esc(d.company.name) + '</h3>';
      if (!d.published) {
        html += '<p class="muted">' + esc(d.message) + '</p>';
        if (d.below_threshold) {
          html += '<p class="small muted">Exact counts stay hidden below the threshold — privacy first, always.</p>';
        }
        html += '<a class="btn secondary" href="/rate">Rate this workplace →</a></div>';
        el.innerHTML = html;
        return;
      }
      var s = d.scores;
      html += '<p class="count-pill">' + d.n_raters + ' raters · index ' + (s.index == null ? '—' : s.index) + ' / 100</p>';
      if (s.vs_expected) {
        var msg = { within_range: 'within the expected range for rated workplaces',
                    above_range: 'above the expected range — a genuine positive signal',
                    below_range: 'below the expected range — a genuine signal, worth attention' }[s.vs_expected];
        html += '<p class="small ' + (s.vs_expected === 'within_range' ? 'muted' : 'amber') + '">' + msg + '</p>';
      }
      Object.keys(PILLAR_LABEL).forEach(function (p) {
        html += bar(PILLAR_LABEL[p], s.pillars[p]);
      });
      if (s.pulse_divergence != null) {
        html += '<p class="small muted">Invited vs. organic divergence: ' + s.pulse_divergence + ' index points (published for integrity).</p>';
      }
      html += '</div>';
      el.innerHTML = html;
    } catch (e) { toast(e.message); }
  }

  loadGlobal();
})();
