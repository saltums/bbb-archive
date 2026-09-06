(function () {
  "use strict";

  // --- ハンバーガーメニュー ---
  const navToggle = document.getElementById("navToggle");
  const navDropdown = document.getElementById("navDropdown");
  if (navToggle && navDropdown) {
    navToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = !navDropdown.hidden;
      navDropdown.hidden = open;
      navToggle.setAttribute("aria-expanded", String(!open));
    });
    document.addEventListener("click", (e) => {
      if (!navDropdown.hidden && !navDropdown.contains(e.target) && e.target !== navToggle) {
        navDropdown.hidden = true;
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  const TYPE_LABEL = {
    release: "リリース",
    live: "ライブ",
    milestone: "できごと",
  };

  const list = document.getElementById("timelineList");
  const overlay = document.getElementById("detailOverlay");
  const closeBtn = document.getElementById("detailClose");
  const majorOnlyToggle = document.getElementById("majorOnlyToggle");
  const filterBtns = document.querySelectorAll(".filter-btn");

  let activeFilter = "all";

  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      activeFilter = btn.dataset.filter;
      filterBtns.forEach((b) => b.classList.toggle("filter-btn--active", b === btn));
      render(allEvents);
    });
  });

  let sentimentByEventId = new Map();
  let allEvents = [];

  // --- 吹き出し管理 ---
  let activeBubble = null;
  let bubbleTimer = null;
  const lastBubbleIdx = new Map(); // anchorEl → 前回のインデックス

  function showBubble(anchorEl, comments, sentimentObj) {
    // 既存の吹き出しを閉じる
    if (activeBubble) dismissBubble(activeBubble);

    // 前回と同じコメントを避ける
    const prev = lastBubbleIdx.get(anchorEl);
    let idx;
    if (comments.length <= 1) {
      idx = 0;
    } else {
      do { idx = Math.floor(Math.random() * comments.length); } while (idx === prev);
    }
    lastBubbleIdx.set(anchorEl, idx);

    // コメントは文字列 or {text, source, source_url} オブジェクトに対応
    const raw = comments[idx];
    const text       = typeof raw === "string" ? raw : raw.text;
    const srcLabel   = typeof raw === "string" ? "5ch ファンの声" : (raw.source || "5ch ファンの声");
    const srcUrl     = typeof raw === "string" ? null : (raw.source_url || null);

    const allPos = (sentimentObj.positive || []).map((c) => typeof c === "string" ? c : c.text);
    const isPos  = allPos.includes(text);

    const srcHtml = srcUrl
      ? `<a class="tl-bubble__source-link" href="${srcUrl}" target="_blank" rel="noopener">${srcLabel}</a>`
      : `<span>${srcLabel}</span>`;

    const bubble = document.createElement("div");
    bubble.className = "tl-bubble" + (isPos ? " tl-bubble--pos" : " tl-bubble--neg");
    bubble.innerHTML = `
      <p class="tl-bubble__text">${text}</p>
      <p class="tl-bubble__source">${srcHtml} · ${isPos ? "好意的" : "批判的"}</p>
    `;
    document.body.appendChild(bubble);
    activeBubble = bubble;

    // アンカー位置を計算してfixedで配置
    const rect = anchorEl.getBoundingClientRect();
    const bubbleW = Math.min(320, window.innerWidth - 32);
    let left = rect.left;
    if (left + bubbleW > window.innerWidth - 16) left = window.innerWidth - bubbleW - 16;
    if (left < 16) left = 16;
    bubble.style.width = bubbleW + "px";
    bubble.style.left = left + "px";
    bubble.style.top = (rect.bottom + 10) + "px";

    // 5秒後に自動消去
    bubbleTimer = setTimeout(() => dismissBubble(bubble), 5000);

    // 外タップで消去
    const onOutside = (e) => {
      if (!bubble.contains(e.target) && e.target !== anchorEl) {
        dismissBubble(bubble);
        document.removeEventListener("click", onOutside, true);
      }
    };
    setTimeout(() => document.addEventListener("click", onOutside, true), 50);
  }

  function dismissBubble(bubble) {
    clearTimeout(bubbleTimer);
    bubble.classList.add("tl-bubble--out");
    setTimeout(() => { if (bubble.parentNode) bubble.remove(); }, 700);
    if (activeBubble === bubble) activeBubble = null;
  }

  // --- ユーティリティ ---
  function toDays(dateStr) {
    return new Date(dateStr + "T00:00:00Z").getTime() / 86400000;
  }

  function formatDate(ev) {
    const [y, m, d] = ev.date.split("-");
    if (ev.date_precision === "year") return `${y}年`;
    if (ev.date_precision === "month") return `${y}年${Number(m)}月`;
    return `${y}年${Number(m)}月${Number(d)}日`;
  }

  function shortDate(ev) {
    const [y, m, d] = ev.date.split("-");
    if (ev.date_precision === "year") return `${y}`;
    if (ev.date_precision === "month") return `${y}/${Number(m)}`;
    return `${y}/${Number(m)}/${Number(d)}`;
  }

  function shortDateStr(dateStr) {
    const [y, m, d] = dateStr.split("-");
    return `${y}/${Number(m)}/${Number(d)}`;
  }

  function buildEmbed(ev) {
    if (!ev.embed) return "";
    const { provider, kind, id } = ev.embed;
    if (provider === "spotify") {
      return `<iframe src="https://open.spotify.com/embed/${kind}/${id}" height="152" allow="encrypted-media" loading="lazy"></iframe>`;
    }
    return "";
  }

  // --- 詳細パネル ---
  function openDetail(ev) {
    document.getElementById("detailDate").textContent =
      `${formatDate(ev)} ・ ${TYPE_LABEL[ev.type] || ev.type}${ev.date_confidence === "estimated" ? "（時期は推定）" : ""}`;
    document.getElementById("detailTitle").textContent = ev.title;
    document.getElementById("detailDesc").textContent = ev.description || "";
    document.getElementById("detailEmbed").innerHTML = buildEmbed(ev);

    const linksEl = document.getElementById("detailLinks");
    linksEl.innerHTML = "";
    (ev.external_links || []).forEach((link) => {
      const a = document.createElement("a");
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = `↗ ${link.label}`;
      linksEl.appendChild(a);
    });

    const sourceEl = document.getElementById("detailSource");
    if (ev.source_url) {
      sourceEl.innerHTML = `出典: <a href="${ev.source_url}" target="_blank" rel="noopener">${ev.source_label || ev.source_url}</a>`;
    } else {
      sourceEl.textContent = "";
    }

    overlay.hidden = false;
  }

  function closeDetail() { overlay.hidden = true; }

  closeBtn.addEventListener("click", closeDetail);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeDetail(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !overlay.hidden) closeDetail(); });

  // --- 年表レンダリング ---

  function appendEvent(ev) {
    const s = sentimentByEventId.get(String(ev.id));
    const allComments = s ? [...(s.positive || []), ...(s.negative || [])] : [];
    const hasBubble = allComments.length > 0;
    const hasLinks = ev.external_links && ev.external_links.length > 0;

    const wrap = document.createElement("div");
    wrap.className = `tl-item-wrap tl-item--${ev.type} tl-item--${ev.importance === "minor" ? "minor" : "major"}`;

    const btn = document.createElement("button");
    btn.className = "tl-item__btn";
    btn.innerHTML = `
      <span class="tl-item__rail"><span class="tl-item__dot"></span></span>
      <span class="tl-item__body">
        <span class="tl-item__date">${shortDate(ev)} ・ ${TYPE_LABEL[ev.type] || ev.type}</span>
        <span class="tl-item__title">${ev.title}${hasLinks ? ' <span class="tl-link-badge" title="リンクあり">🔗</span>' : ''}</span>
      </span>
    `;
    btn.addEventListener("click", () => openDetail(ev));
    wrap.appendChild(btn);

    if (hasBubble) {
      const bubbleBtn = document.createElement("button");
      bubbleBtn.className = "tl-bubble-btn";
      bubbleBtn.setAttribute("aria-label", "当時のファンの声を見る");
      bubbleBtn.textContent = "💬";
      bubbleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        showBubble(bubbleBtn, allComments, s);
      });
      wrap.appendChild(bubbleBtn);
    }

    list.appendChild(wrap);
  }

  function appendTourGroup(group, tourName) {
    const container = document.createElement("div");
    container.className = "tl-tour-group";

    // ヘッダー行（ツアー名・日程レンジ・公演数）
    const headerRow = document.createElement("div");
    headerRow.className = "tl-item-wrap tl-item--live tl-item--major";

    const startShort = shortDateStr(group.lastDate);
    const endShort = shortDateStr(group.firstDate);
    const dateRange = group.events.length === 1 ? startShort : `${startShort}〜${endShort}`;
    const count = group.events.length;
    const hasLinks = group.events.some((ev) => ev.external_links && ev.external_links.length > 0);

    const headerBtn = document.createElement("button");
    headerBtn.className = "tl-item__btn";
    headerBtn.innerHTML = `
      <span class="tl-item__rail"><span class="tl-item__dot"></span></span>
      <span class="tl-item__body">
        <span class="tl-item__date">${dateRange} ・ ライブ ・ 全${count}公演</span>
        <span class="tl-item__title">${tourName}${hasLinks ? ' <span class="tl-link-badge" title="リンクあり">🔗</span>' : ''} <span class="tl-tour-chevron" aria-hidden="true">▶</span></span>
      </span>
    `;

    // 公演リスト（初期非表示）
    const showsList = document.createElement("div");
    showsList.className = "tl-tour-shows";
    showsList.hidden = true;

    group.events.forEach((ev) => {
      const s2 = sentimentByEventId.get(String(ev.id));
      const allC = s2 ? [...(s2.positive || []), ...(s2.negative || [])] : [];
      const hasEvLinks = ev.external_links && ev.external_links.length > 0;

      const showWrap = document.createElement("div");
      showWrap.className = "tl-item-wrap tl-item--live tl-item--minor";

      const showBtn = document.createElement("button");
      showBtn.className = "tl-item__btn";
      showBtn.innerHTML = `
        <span class="tl-item__rail"><span class="tl-item__dot"></span></span>
        <span class="tl-item__body">
          <span class="tl-item__date">${shortDate(ev)}</span>
          <span class="tl-item__title">${ev.title}${hasEvLinks ? ' <span class="tl-link-badge" title="リンクあり">🔗</span>' : ''}</span>
        </span>
      `;
      showBtn.addEventListener("click", () => openDetail(ev));
      showWrap.appendChild(showBtn);

      if (allC.length > 0) {
        const bb = document.createElement("button");
        bb.className = "tl-bubble-btn";
        bb.setAttribute("aria-label", "当時のファンの声を見る");
        bb.textContent = "💬";
        bb.addEventListener("click", (e) => { e.stopPropagation(); showBubble(bb, allC, s2); });
        showWrap.appendChild(bb);
      }

      showsList.appendChild(showWrap);
    });

    headerBtn.addEventListener("click", () => {
      const opening = showsList.hidden;
      showsList.hidden = !opening;
      headerBtn.querySelector(".tl-tour-chevron").textContent = opening ? "▼" : "▶";
    });

    headerRow.appendChild(headerBtn);
    container.appendChild(headerRow);
    container.appendChild(showsList);
    list.appendChild(container);
  }

  function render(events) {
    list.innerHTML = "";
    if (!events || events.length === 0) {
      list.innerHTML = '<p style="color:var(--ink-dim);padding:1rem;">年表データがありません。</p>';
      return;
    }

    const typeFiltered = activeFilter === "all"
      ? events
      : events.filter((ev) => ev.type === activeFilter);
    const filtered = majorOnlyToggle && majorOnlyToggle.checked
      ? typeFiltered.filter((ev) => ev.importance === "major")
      : typeFiltered;
    const sorted = [...filtered].sort((a, b) => toDays(b.date) - toDays(a.date));
    const cutoffDay = toDays(new Date().toISOString().slice(0, 10)) - 5 * 365.25;

    // ツアーグループを構築（2公演以上のツアーのみ）
    const tourMap = new Map();
    sorted.forEach((ev) => {
      if (ev.type === "live" && ev.tour) {
        if (!tourMap.has(ev.tour)) {
          tourMap.set(ev.tour, { events: [], firstDate: ev.date, lastDate: ev.date });
        }
        const g = tourMap.get(ev.tour);
        g.events.push(ev);
        if (toDays(ev.date) > toDays(g.firstDate)) g.firstDate = ev.date;
        if (toDays(ev.date) < toDays(g.lastDate)) g.lastDate = ev.date;
      }
    });
    const validTours = new Set(
      [...tourMap.entries()].filter(([, g]) => g.events.length >= 2).map(([name]) => name)
    );
    const renderedTours = new Set();

    let lastYearShown = null;
    let cutoffInserted = false;

    sorted.forEach((ev) => {
      if (!cutoffInserted && toDays(ev.date) <= cutoffDay) {
        cutoffInserted = true;
        const cutoff = document.createElement("div");
        cutoff.className = "tl-cutoff";
        cutoff.textContent = "ここから先は5年より前";
        list.appendChild(cutoff);
      }

      const year = ev.date.slice(0, 4);
      if (year !== lastYearShown) {
        lastYearShown = year;
        const heading = document.createElement("div");
        heading.className = "tl-year-heading";
        heading.textContent = `${year}年`;
        list.appendChild(heading);
      }

      if (ev.type === "live" && ev.tour && validTours.has(ev.tour)) {
        if (renderedTours.has(ev.tour)) return;
        renderedTours.add(ev.tour);
        appendTourGroup(tourMap.get(ev.tour), ev.tour);
      } else {
        appendEvent(ev);
      }
    });
  }

  if (majorOnlyToggle) {
    majorOnlyToggle.addEventListener("change", () => render(allEvents));
  }

  async function fetchEvents() {
    const cfg = window.SUPABASE_CONFIG;
    if (cfg && cfg.url && cfg.anonKey) {
      // Supabase REST API — fetch all events ordered by date
      const url = `${cfg.url}/rest/v1/timeline_events?select=*&order=date.asc&limit=2000`;
      const res = await fetch(url, {
        headers: {
          apikey: cfg.anonKey,
          Authorization: `Bearer ${cfg.anonKey}`,
        },
      });
      if (!res.ok) throw new Error(`Supabase ${res.status}`);
      return res.json();
    }
    // Fallback: static JSON
    const res = await fetch("data/timeline.json", { cache: "no-store" });
    return res.ok ? res.json() : [];
  }

  Promise.all([
    fetchEvents(),
    fetch("data/sentiment-manual.json", { cache: "no-store" }).then((res) => (res.ok ? res.json() : [])).catch(() => []),
  ])
    .then(([events, sentiment]) => {
      sentimentByEventId = new Map((sentiment || []).map((s) => [String(s.event_id), s]));
      allEvents = events || [];
      render(allEvents);
    })
    .catch((err) => {
      console.error("年表データの読み込みに失敗しました", err);
      list.innerHTML = '<p style="color:#ff5470;padding:1rem;">年表データの読み込みに失敗しました。</p>';
    });
})();
