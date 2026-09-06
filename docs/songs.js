(function () {
  "use strict";

  const list = document.getElementById("songAlbumList");
  const kpis = document.getElementById("songKpis");
  const filterBar = document.getElementById("songFilterBar");

  const TYPE_LABEL = {
    album:   "アルバム",
    mini:    "ミニアルバム",
    ep:      "EP",
    single:  "シングル",
    digital: "配信シングル",
    indie:   "インディーズ",
  };

  const TYPE_ORDER = ["album", "mini", "ep", "single", "digital", "indie"];

  let allReleases = [];
  let activeFilter = "all";

  // --- フィルタボタン ---
  function buildFilterBar(releases) {
    if (!filterBar) return;
    const types = TYPE_ORDER.filter((t) => releases.some((r) => r.type === t));
    const btns = [
      { key: "all", label: "すべて" },
      ...types.map((t) => ({ key: t, label: TYPE_LABEL[t] || t })),
    ];
    filterBar.innerHTML = btns
      .map(
        (b) =>
          `<button class="filter-btn${activeFilter === b.key ? " filter-btn--active" : ""}" data-filter="${b.key}">${b.label}</button>`
      )
      .join("");
    filterBar.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeFilter = btn.dataset.filter;
        render(allReleases);
      });
    });
  }

  // --- 楽曲リンクHTML ---
  function trackLinksHtml(links) {
    if (!links || links.length === 0) return "";
    return links
      .map(
        (lk) =>
          `<a class="sl-track-link" href="${lk.url}" target="_blank" rel="noopener" title="${lk.label}">🔗</a>`
      )
      .join("");
  }

  // --- レンダリング ---
  function render(releases) {
    buildFilterBar(releases);

    const filtered =
      activeFilter === "all"
        ? releases
        : releases.filter((r) => r.type === activeFilter);

    const sorted = [...filtered].sort((a, b) =>
      a.release_date < b.release_date ? 1 : -1
    );

    // KPI
    const allTitles = new Set(
      releases.flatMap((r) => r.tracks.map((t) => (typeof t === "string" ? t : t.title)))
    );
    if (kpis) {
      kpis.innerHTML = `
        <div class="sl-kpi"><div class="sl-kpi__value">${releases.length}</div><div class="sl-kpi__label">収録作品数</div></div>
        <div class="sl-kpi"><div class="sl-kpi__value">${allTitles.size}</div><div class="sl-kpi__label">楽曲数(ユニーク)</div></div>
      `;
    }

    if (!sorted || sorted.length === 0) {
      list.innerHTML = '<p class="sl-empty">楽曲データがありません。</p>';
      return;
    }

    list.innerHTML = "";
    sorted.forEach((release) => {
      const typeLabel = TYPE_LABEL[release.type] || release.type;
      const year = release.release_date ? release.release_date.slice(0, 4) : "";
      const card = document.createElement("article");
      card.className = "sl-show sl-show--release";

      const hasAnyLinks = release.tracks.some(
        (t) => typeof t !== "string" && t.external_links && t.external_links.length > 0
      );

      card.innerHTML = `
        <div class="sl-show__head">
          <span class="sl-show__title">${release.album_title}${hasAnyLinks ? ' <span class="tl-link-badge" title="リンクあり">🔗</span>' : ""}</span>
          <span class="song-type-tag song-type-tag--${release.type}">${typeLabel}</span>
          <span class="sl-show__venue">${year}</span>
        </div>
        <div class="sl-show__body">
          <ol class="sl-track-list">
            ${release.tracks
              .map((t) => {
                if (typeof t === "string") {
                  return `<li class="sl-track-item"><span class="sl-track-title">${t}</span></li>`;
                }
                const noteHtml = t.note ? ` <span class="sl-track-note">${t.note}</span>` : "";
                const linksHtml = trackLinksHtml(t.external_links);
                return `<li class="sl-track-item${t.external_links && t.external_links.length ? " sl-track-item--linked" : ""}">
                  <span class="sl-track-title">${t.title}${noteHtml}</span>
                  ${linksHtml ? `<span class="sl-track-links">${linksHtml}</span>` : ""}
                </li>`;
              })
              .join("")}
          </ol>
          ${release.note ? `<p class="sl-section__note">${release.note}</p>` : ""}
          ${release.source_url ? `<p class="sl-show__source">出典: <a href="${release.source_url}" target="_blank" rel="noopener">${release.source_label || release.source_url}</a></p>` : ""}
        </div>
      `;

      card.querySelector(".sl-show__head").addEventListener("click", () =>
        card.classList.toggle("is-open")
      );
      list.appendChild(card);
    });
  }

  fetch("data/songs.json", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : []))
    .then((data) => {
      allReleases = data || [];
      render(allReleases);
    })
    .catch((err) => {
      console.error("楽曲データの読み込みに失敗しました", err);
      render([]);
    });
})();
