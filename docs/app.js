(function () {
  "use strict";

  const TYPE_LABEL = {
    release: "リリース",
    live: "ライブ",
    milestone: "できごと",
  };

  const list = document.getElementById("timelineList");
  const overlay = document.getElementById("detailOverlay");
  const closeBtn = document.getElementById("detailClose");
  const majorOnlyToggle = document.getElementById("majorOnlyToggle");

  let sentimentByEventId = new Map();
  let allEvents = [];

  function toDays(dateStr) {
    return new Date(dateStr + "T00:00:00Z").getTime() / 86400000;
  }

  function formatDate(ev) {
    const [y, m, d] = ev.date.split("-");
    if (ev.date_precision === "year") return `${y}年`;
    if (ev.date_precision === "month") return `${y}年${Number(m)}月`;
    return `${y}年${Number(m)}月${Number(d)}日`;
  }

  function buildEmbed(ev) {
    if (!ev.embed) return "";
    const { provider, kind, id } = ev.embed;
    if (provider === "spotify") {
      return `<iframe src="https://open.spotify.com/embed/${kind}/${id}" height="152" allow="encrypted-media" loading="lazy"></iframe>`;
    }
    return "";
  }

  function buildSentiment(ev) {
    const s = sentimentByEventId.get(String(ev.id));
    if (!s) return "";
    const posItems = (s.positive || []).map((t) => `<li>${t}</li>`).join("");
    const negItems = (s.negative || []).map((t) => `<li>${t}</li>`).join("");
    if (!posItems && !negItems) return "";
    return `
      <div class="detail-sentiment">
        <p class="detail-sentiment__heading">当時の反応(世論)</p>
        ${posItems ? `<div class="detail-sentiment__col detail-sentiment__col--pos"><p>ポジティブ</p><ul>${posItems}</ul></div>` : ""}
        ${negItems ? `<div class="detail-sentiment__col detail-sentiment__col--neg"><p>ネガティブ</p><ul>${negItems}</ul></div>` : ""}
        ${s.note ? `<p class="detail-sentiment__note">${s.note}</p>` : ""}
      </div>
    `;
  }

  function openDetail(ev) {
    document.getElementById("detailDate").textContent = `${formatDate(ev)} ・ ${TYPE_LABEL[ev.type] || ev.type}${ev.date_confidence === "estimated" ? "(時期は推定)" : ""}`;
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

    let sentimentEl = document.getElementById("detailSentiment");
    if (!sentimentEl) {
      sentimentEl = document.createElement("div");
      sentimentEl.id = "detailSentiment";
      document.getElementById("detailLinks").insertAdjacentElement("afterend", sentimentEl);
    }
    sentimentEl.innerHTML = buildSentiment(ev);

    const sourceEl = document.getElementById("detailSource");
    if (ev.source_url) {
      sourceEl.innerHTML = `出典: <a href="${ev.source_url}" target="_blank" rel="noopener">${ev.source_label || ev.source_url}</a>`;
    } else {
      sourceEl.textContent = "";
    }

    overlay.hidden = false;
  }

  function closeDetail() {
    overlay.hidden = true;
  }

  closeBtn.addEventListener("click", closeDetail);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeDetail();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.hidden) closeDetail();
  });

  function shortDate(ev) {
    const [y, m, d] = ev.date.split("-");
    if (ev.date_precision === "year") return `${y}`;
    if (ev.date_precision === "month") return `${y}/${Number(m)}`;
    return `${y}/${Number(m)}/${Number(d)}`;
  }

  function render(events) {
    list.innerHTML = "";
    if (!events || events.length === 0) {
      list.innerHTML = '<p style="color:var(--ink-dim);padding:1rem;">年表データがありません。</p>';
      return;
    }
    const filtered = majorOnlyToggle && majorOnlyToggle.checked ? events.filter((ev) => ev.importance === "major") : events;
    // 新しい出来事が上、結成当時が下(スマホでも自然にたどれる縦一本リスト)
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

      const item = document.createElement("button");
      item.className = `tl-item tl-item--${ev.type} tl-item--${ev.importance === "minor" ? "minor" : "major"}`;
      item.innerHTML = `
        <span class="tl-item__rail"><span class="tl-item__dot"></span></span>
        <span class="tl-item__body">
          <span class="tl-item__date">${shortDate(ev)} ・ ${TYPE_LABEL[ev.type] || ev.type}</span>
          <span class="tl-item__title">${ev.title}</span>
        </span>
      `;
      item.addEventListener("click", () => openDetail(ev));
      list.appendChild(item);
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
