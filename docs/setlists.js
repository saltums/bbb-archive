(function () {
  "use strict";

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function renderEmpty(container, message) {
    container.innerHTML = `<p class="sl-empty">${message}</p>`;
  }

  function allSongs(show) {
    return (show.sets || []).flatMap((s) => s.songs || []);
  }

  function renderKpis(shows) {
    const kpis = document.getElementById("slKpis");
    if (shows.length === 0) {
      renderEmpty(kpis, "まだセットリストデータがありません。scripts/Fetch-Setlists.ps1 → Parse-Setlists.ps1 を実行してください。");
      return;
    }
    const uniqueSongs = new Set(shows.flatMap(allSongs));
    const dates = shows.map((s) => s.date).sort();
    const tiles = [
      { value: shows.length, label: "収録セットリスト数" },
      { value: uniqueSongs.size, label: "収録楽曲数(ユニーク)" },
      { value: `${dates[0].slice(0, 4)}〜${dates[dates.length - 1].slice(0, 4)}`, label: "対象期間" },
    ];
    kpis.innerHTML = tiles
      .map((t) => `<div class="sl-kpi"><div class="sl-kpi__value">${t.value}</div><div class="sl-kpi__label">${t.label}</div></div>`)
      .join("");
  }

  function renderBarList(container, entries, max) {
    container.innerHTML = "";
    entries.forEach(([label, count]) => {
      const pct = Math.max(4, Math.round((count / max) * 100));
      container.appendChild(
        el(`
        <div class="sl-bar-row">
          <div class="sl-bar-row__label" title="${label}">${label}</div>
          <div class="sl-bar-row__track"><div class="sl-bar-row__fill" style="width:${pct}%"></div></div>
          <div class="sl-bar-row__count">${count.toLocaleString("ja-JP")}</div>
        </div>
      `)
      );
    });
  }

  function renderSongRanking(shows) {
    const container = document.getElementById("slSongRanking");
    const counts = new Map();
    shows.forEach((show) => {
      allSongs(show).forEach((song) => counts.set(song, (counts.get(song) || 0) + 1));
    });
    if (counts.size === 0) {
      renderEmpty(container, "曲データがありません。");
      return;
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20);
    renderBarList(container, sorted, sorted[0][1]);
  }

  function renderYearChart(shows) {
    const container = document.getElementById("slYearChart");
    if (shows.length === 0) {
      renderEmpty(container, "データがありません。");
      return;
    }
    const counts = new Map();
    shows.forEach((show) => {
      const y = show.date.slice(0, 4);
      counts.set(y, (counts.get(y) || 0) + 1);
    });
    const years = [...counts.keys()].sort();
    const max = Math.max(...counts.values());
    container.innerHTML = "";
    years.forEach((y) => {
      const count = counts.get(y);
      const heightPct = Math.max(4, Math.round((count / max) * 100));
      container.appendChild(
        el(`
        <div class="sl-bar-col">
          <div class="sl-bar-col__count">${count}</div>
          <div class="sl-bar-col__fill" style="height:${heightPct}%"></div>
          <div class="sl-bar-col__label">${y}</div>
        </div>
      `)
      );
    });
  }

  function renderVenueRanking(shows) {
    const container = document.getElementById("slVenueRanking");
    if (shows.length === 0) {
      renderEmpty(container, "データがありません。");
      return;
    }
    const counts = new Map();
    shows.forEach((show) => {
      if (!show.venue) return;
      counts.set(show.venue, (counts.get(show.venue) || 0) + 1);
    });
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
    if (sorted.length === 0) {
      renderEmpty(container, "会場データがありません。");
      return;
    }
    renderBarList(container, sorted, sorted[0][1]);
  }

  function sourceLine(show) {
    if (show.source === "setlistfm" && show.source_url) {
      return `出典: <a href="${show.source_url}" target="_blank" rel="noopener">${show.venue} setlist on setlist.fm</a>`;
    }
    if (show.source_url) {
      return `出典: <a href="${show.source_url}" target="_blank" rel="noopener">${show.source_label || "情報源"}</a>`;
    }
    return show.source_label ? `出典: ${show.source_label}` : "";
  }

  function renderShowCard(show) {
    const setsHtml = (show.sets || [])
      .map(
        (s) => `
        <div class="sl-set">
          <div class="sl-set__label">${s.label}</div>
          <ol>${(s.songs || []).map((song) => `<li>${song}</li>`).join("")}</ol>
        </div>
      `
      )
      .join("");

    const card = el(`
      <article class="sl-show">
        <div class="sl-show__head">
          <span class="sl-show__date">${show.date}</span>
          <span class="sl-show__venue">${show.venue || ""}${show.city ? " / " + show.city : ""}</span>
        </div>
        <div class="sl-show__body">
          ${setsHtml}
          ${show.note ? `<p class="sl-section__note">${show.note}</p>` : ""}
          <p class="sl-show__source">${sourceLine(show)}</p>
        </div>
      </article>
    `);
    card.querySelector(".sl-show__head").addEventListener("click", () => {
      card.classList.toggle("is-open");
    });
    return card;
  }

  function renderTourSection(shows) {
    const select = document.getElementById("slTourSelect");
    const showsContainer = document.getElementById("slTourShows");

    if (shows.length === 0) {
      select.innerHTML = "";
      renderEmpty(showsContainer, "データがありません。");
      return;
    }

    const tourNames = [...new Set(shows.map((s) => s.tour).filter(Boolean))].sort();
    const hasNoTour = shows.some((s) => !s.tour);
    const options = tourNames.map((t) => `<option value="${t}">${t}</option>`);
    if (hasNoTour) options.push('<option value="__none__">(ツアー名なし・単発公演等)</option>');

    select.innerHTML = options.join("");

    function renderForTour(tourValue) {
      const filtered = shows
        .filter((s) => (tourValue === "__none__" ? !s.tour : s.tour === tourValue))
        .sort((a, b) => (a.date < b.date ? -1 : 1));
      showsContainer.innerHTML = "";
      if (filtered.length === 0) {
        renderEmpty(showsContainer, "このツアーのセットリストはまだありません。");
        return;
      }
      filtered.forEach((show) => showsContainer.appendChild(renderShowCard(show)));
    }

    select.addEventListener("change", () => renderForTour(select.value));
    if (options.length > 0) {
      select.value = tourNames[0] || "__none__";
      renderForTour(select.value);
    }
  }

  function renderYoutubeRanking(data) {
    const container = document.getElementById("slYoutubeRanking");
    const fetchedAtEl = document.getElementById("slYoutubeFetchedAt");
    const videos = (data && data.videos) || [];
    if (videos.length === 0) {
      fetchedAtEl.textContent = "YouTube公式チャンネルの動画データがまだありません。";
      renderEmpty(container, "scripts/Fetch-YouTubeStats.ps1 → Parse-YouTubeStats.ps1 を実行してください。");
      return;
    }
    fetchedAtEl.textContent = `取得日: ${data.fetched_at}(YouTube公式チャンネルの動画。再生回数はこの時点のスナップショットです)`;
    const top = videos.slice(0, 20).map((v) => [v.title, v.viewCount]);
    renderBarList(container, top, top[0][1]);
    // タイトルをクリックで動画を開けるようにリンク化
    [...container.querySelectorAll(".sl-bar-row__label")].forEach((el, i) => {
      const v = videos[i];
      el.innerHTML = `<a href="${v.url}" target="_blank" rel="noopener" title="${v.title}">${v.title}</a>`;
    });
  }

  function render(shows, youtube) {
    renderKpis(shows);
    renderSongRanking(shows);
    renderYearChart(shows);
    renderVenueRanking(shows);
    renderYoutubeRanking(youtube);
    renderTourSection(shows);
  }

  Promise.all([
    fetch("data/setlists.json", { cache: "no-store" }).then((res) => (res.ok ? res.json() : [])),
    fetch("data/youtube-stats.json", { cache: "no-store" }).then((res) => (res.ok ? res.json() : null)).catch(() => null),
  ])
    .then(([shows, youtube]) => render(shows, youtube))
    .catch((err) => {
      console.error("データの読み込みに失敗しました", err);
      render([], null);
    });
})();
