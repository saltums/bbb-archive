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

      // sentimentデータがあるか確認
      const s = sentimentByEventId.get(String(ev.id));
      const allComments = s ? [...(s.positive || []), ...(s.negative || [])] : [];
      const hasBubble = allComments.length > 0;

      // ラッパーdiv（本体ボタン + 吹き出しボタンを横並び）
      const wrap = document.createElement("div");
      wrap.className = `tl-item-wrap tl-item--${ev.type} tl-item--${ev.importance === "minor" ? "minor" : "major"}`;

      // 本体ボタン
      const btn = document.createElement("button");
      btn.className = "tl-item__btn";
      btn.innerHTML = `
        <span class="tl-item__rail"><span class="tl-item__dot"></span></span>
        <span class="tl-item__body">
          <span class="tl-item__date">${shortDate(ev)} ・ ${TYPE_LABEL[ev.type] || ev.type}</span>
          <span class="tl-item__title">${ev.title}</span>
        </span>
      `;
      btn.addEventListener("click", () => openDetail(ev));
      wrap.appendChild(btn);

      // 吹き出しボタン（sentimentあるイベントのみ）
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
    });
  }

  if (majorOnlyToggle) {
    majorOnlyToggle.addEventListener("change", () => render(allEvents));
  }

  Promise.all([
    fetch("data/timeline.json", { cache: "no-store" }).then((res) => (res.ok ? res.json() : [])),
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
