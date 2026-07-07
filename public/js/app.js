/* ============================================================
   Rate My Systems — rating flow (app.js)
   Vanilla JS. No frameworks. Items are issued by the server;
   this file never knows the item bank.
   ============================================================ */
(function () {
  'use strict';

  var state = { company: null, session: null, items: [], anchors: [], answers: {}, idx: 0 };

  function $(id) { return document.getElementById(id); }
  function show(id) { $(id).classList.remove('hidden'); }
  function hide(id) { $(id).classList.add('hidden'); }
  function esc(s) {
    return (s == null ? '' : String(s))
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    $('toast-root').appendChild(el);
    setTimeout(function () { el.remove(); }, 4500);
  }

  async function api(path, opts) {
    var res = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin'
    }, opts || {}));
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok || data.ok === false) {
      throw new Error((data && data.detail) || ('Request failed (' + res.status + ')'));
    }
    return data;
  }

  /* ---------- STEP 0: auth / membership gate ---------- */
  var PROVIDER_LABELS = { google: 'Continue with Google', github: 'Continue with GitHub', apple: 'Continue with Apple' };

  async function initAuth() {
    var me = {}, providers = {};
    try { me = await api('/v1/auth/me'); } catch (e) {}
    try { providers = await api('/v1/auth/providers'); } catch (e) {}

    if (me.signed_in) {
      var w = $('whoami');
      w.innerHTML = 'Signed in as ' + esc(me.handle) + ' · <a href="#" id="signout">sign out</a>';
      w.classList.remove('hidden');
      var so = document.getElementById('signout');
      if (so) so.addEventListener('click', async function (ev) {
        ev.preventDefault();
        try { await api('/v1/auth/logout', { method: 'POST', headers: { 'X-CSRF': me.csrf || '' } }); } catch (e) {}
        location.reload();
      });
      show('screen-company');
      return;
    }

    if (providers.require_login) {
      // Build sign-in screen from whatever methods are live.
      var box = $('social-buttons');
      box.innerHTML = '';
      (providers.oauth || []).forEach(function (p) {
        var b = document.createElement('button');
        b.className = 'btn';
        b.textContent = PROVIDER_LABELS[p] || ('Continue with ' + p);
        b.addEventListener('click', function () { window.location = '/v1/auth/oauth/' + p + '/login'; });
        box.appendChild(b);
      });
      if (providers.email) $('email-login').classList.remove('hidden');
      $('login-email-btn').addEventListener('click', doEmailLogin);
      show('screen-login');
      return;
    }

    // Login optional — go straight to rating.
    show('screen-company');
  }

  async function doEmailLogin() {
    var email = ($('login-email').value || '').trim();
    if (!email) { $('login-msg').textContent = 'Enter your email first.'; return; }
    $('login-email-btn').disabled = true;
    try {
      await api('/v1/auth/magic-link', { method: 'POST', body: JSON.stringify({ email: email }) });
      $('login-msg').textContent = 'Check your email for a sign-in link, then come back and rate.';
    } catch (e) {
      $('login-msg').textContent = e.message;
      $('login-email-btn').disabled = false;
    }
  }

  /* ---------- STEP 1: company ---------- */
  var searchTimer = null;
  $('company-search').addEventListener('input', function () {
    clearTimeout(searchTimer);
    var q = this.value.trim();
    searchTimer = setTimeout(function () { searchCompanies(q); }, 250);
  });

  async function searchCompanies(q) {
    try {
      var data = await api('/v1/companies?q=' + encodeURIComponent(q));
      var ul = $('company-results');
      ul.innerHTML = '';
      data.companies.forEach(function (c) {
        var li = document.createElement('li');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = c.name;
        btn.addEventListener('click', function () { pickCompany(c); });
        li.appendChild(btn);
        ul.appendChild(li);
      });
      var addBtn = $('company-add');
      if (q.length >= 2) {
        addBtn.textContent = 'Add “' + q + '” & continue →';
        addBtn.dataset.name = q;
        show('company-add');
      } else {
        hide('company-add');
      }
    } catch (e) { toast(e.message); }
  }

  $('company-add').addEventListener('click', async function () {
    try {
      var data = await api('/v1/companies', { method: 'POST', body: JSON.stringify({ name: this.dataset.name }) });
      pickCompany(data.company);
    } catch (e) { toast(e.message); }
  });

  async function pickCompany(c) {
    state.company = c;
    try {
      var s = await api('/v1/session/new', { method: 'POST', body: JSON.stringify({ company_id: c.id }) });
      state.session = s.session_id;
      state.items = s.items;
      state.anchors = s.anchors;
      state.idx = 0;
      state.answers = {};
      hide('screen-company');
      show('screen-flow');
      renderItem();
    } catch (e) { toast(e.message); }
  }

  /* ---------- STEP 2: items ---------- */
  function renderItem() {
    var total = state.items.length;
    var i = state.idx;
    if (i >= total) {
      hide('screen-flow');
      show('screen-comment');
      window.scrollTo(0, 0);
      return;
    }
    var item = state.items[i];
    $('progress').textContent = (i + 1) + ' / ' + total;

    var html = '<div class="stack">';
    html += '<p class="cat-name">' + esc(item.category_label) + '</p>';
    html += '<p class="cat-prompt">' + esc(item.text) + '</p>';
    html += '<div class="scale" role="group" aria-label="Answer">';
    for (var v = 1; v <= 5; v++) {
      html += '<button type="button" data-v="' + v + '">' +
              '<span class="scale-num">' + v + '</span>' +
              '<span class="scale-anchor">' + esc(state.anchors[v - 1]) + '</span></button>';
    }
    html += '</div></div>';
    $('flow').innerHTML = html;

    Array.prototype.forEach.call(document.querySelectorAll('.scale button'), function (btn) {
      btn.addEventListener('click', function () {
        state.answers[item.key] = parseInt(this.dataset.v, 10);
        state.idx += 1;
        renderItem();
      });
    });
    window.scrollTo(0, 0);
  }

  /* ---------- STEP 3: submit ---------- */
  $('submit-rating').addEventListener('click', doSubmit);

  async function doSubmit() {
    $('submit-rating').disabled = true;
    try {
      var body = {
        session_id: state.session,
        answers: state.answers,
        comment: ($('comment-text').value || '').trim() || null,
        website: $('website').value || null
      };
      var data = await api('/v1/submit', { method: 'POST', body: JSON.stringify(body) });
      renderResult(data.comparison);
    } catch (e) {
      toast(e.message);
      $('submit-rating').disabled = false;
    }
  }

  /* ---------- STEP 4: instant comparison (A3) ---------- */
  function bar(label, value, outOf) {
    outOf = outOf || 5;
    var pct = value == null ? 0 : (value / outOf) * 100;
    return '<div class="bar-row"><div class="bar-head"><span>' + esc(label) + '</span>' +
      '<span class="val">' + (value == null ? '—' : value) + '</span></div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div></div>';
  }

  function renderResult(c) {
    hide('screen-comment');
    show('screen-result');
    window.scrollTo(0, 0);

    $('result-score').textContent = c.your_index;

    var exp = c.expected || {};
    var expEl = $('result-expected');
    if (exp.expected_low != null) {
      var pos = c.your_index < exp.expected_low ? 'below' :
                c.your_index > exp.expected_high ? 'above' : 'within';
      expEl.textContent = pos + ' the expected range (' + exp.expected_low + '–' + exp.expected_high +
        ') across ' + exp.n_companies + ' rated workplaces';
    } else if (c.percentile_vs_rated != null) {
      expEl.textContent = 'higher than ' + c.percentile_vs_rated + '% of rated workplaces so far';
    } else {
      expEl.textContent = 'among the first workplaces rated — the expected range builds as ratings come in';
    }

    $('result-strength').innerHTML =
      '<div class="bar-head"><span class="amber">Strongest system</span></div>' +
      bar(c.strength.label, c.strength.score);
    $('result-gap').innerHTML =
      '<div class="bar-head"><span>Biggest gap</span></div>' +
      bar(c.gap.label, c.gap.score);

    var cons = $('result-consensus');
    if (c.consensus && c.consensus.same_gap_as_global) {
      cons.textContent = 'Across everyone rated so far, the most common weak system is the same one you flagged: ' +
        c.gap.label + '. Not a coincidence — and not a you problem.';
    } else if (c.global_n > 0) {
      cons.textContent = 'One rating is an opinion. Thousands are a diagnosis. Yours just sharpened the picture.';
    } else {
      cons.textContent = 'You are among the very first raters. The picture starts with you.';
    }

    var cats = '';
    Object.keys(c.your_categories).forEach(function (k) {
      cats += bar(k, c.your_categories[k]);
    });
    $('result-categories').innerHTML = cats;
  }

  // Decide the first screen (sign-in gate vs. straight to rating).
  initAuth();
})();
