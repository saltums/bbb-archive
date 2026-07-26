(function () {
  "use strict";

  const list = document.getElementById("songAlbumList");
  const kpis = document.getElementById("songKpis");

  const TYPE_LABEL = { single: "シングル", album: "アルバム", ep: "EP" };

  function render(albums) {
    if (!albums || albums.length === 0) {
      list.innerHTML = '<p class="sl-empty">まだ楽曲データがありません。</p>';
      return;
    }
    const sorted = [...albums].sort((a, b) => (a.release_date < b.release_date ? 1 : -1));

    const totalSongs = new Set(sorted.flatMap((a) => a.tracks)).size;
    if (kpis) {
      kpis.innerHTML = `
        <div class="sl-kpi"><div class="sl-kpi__value">${sorted.length}</div><div class="sl-kpi__label">収録作品数</div></div>
        <div class="sl-kpi"><div class="sl-kpi__value">${totalSongs}</div><div class="sl-kpi__label">収録曲数(のべ)</div></div>
      `;
    }

    list.innerHTML = "";
    sorted.forEach((album) => {
      const typeLabel = TYPE_LABEL[album.type] || "アルバム";
      const card = document.createElement("article");
      card.className = "sl-show";
      card.innerHTML = `
        <div class="sl-show__head">
          <span class="sl-show__date">${album.album_title} <span class="song-type-tag">${typeLabel}</span></span>
          <span class="sl-show__venue">${album.release_date}</span>
        </div>
        <div class="sl-show__body">
          <ol style="margin:0;padding-left:1.4rem;font-size:0.88rem;line-height:1.8;">
            ${album.tracks.map((t) => `<li>${t}</li>`).join("")}
          </ol>
          ${album.note ? `<p class="sl-section__note">${album.note}</p>` : ""}
          <p class="sl-show__source">出典: <a href="${album.source_url}" target="_blank" rel="noopener">${album.source_label}</a></p>
        </div>
      `;
      card.querySelector(".sl-show__head").addEventListener("click", () => card.classList.toggle("is-open"));
      list.appendChild(card);
    });
  }

  fetch("data/songs.json", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : []))
    .then(render)
    .catch((err) => {
      console.error("楽曲データの読み込みに失敗しました", err);
      render([]);
    });
})();
