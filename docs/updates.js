(function () {
  "use strict";

  const list = document.getElementById("upList");

  function render(items) {
    if (!items || items.length === 0) {
      list.innerHTML = '<p class="sl-empty" style="border:1px dashed var(--line);border-radius:14px;padding:1.5rem;text-align:center;color:var(--ink-dim);">まだ情報がありません。data/updates-manual.json に追記すると、ここに表示されます。</p>';
      return;
    }
    list.innerHTML = items
      .map((item) => {
        const source =
          item.source_url && item.source_label
            ? `<a href="${item.source_url}" target="_blank" rel="noopener">${item.source_label}</a>`
            : item.source_label || "";
        return `
          <article class="up-item">
            <div class="up-item__date">${item.date}</div>
            <h2 class="up-item__title">${item.title}</h2>
            <p class="up-item__body">${item.body || ""}</p>
            ${source ? `<p class="up-item__source">出典: ${source}</p>` : ""}
          </article>
        `;
      })
      .join("");
  }

  fetch("data/updates.json", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : []))
    .then(render)
    .catch((err) => {
      console.error("最新情報の読み込みに失敗しました", err);
      render([]);
    });
})();
