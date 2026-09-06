(function () {
  "use strict";

  // ─── nav hamburger (same pattern as app.js) ───
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
      if (!navDropdown.hidden && !navDropdown.contains(e.target) && e.target !== navToggle)
        navDropdown.hidden = true;
    });
  }

  // ─── city → prefecture map ───
  const PREF = {
    "東京":"東京都","渋谷":"東京都","下北沢":"東京都","新宿":"東京都","池袋":"東京都","六本木":"東京都",
    "横浜":"神奈川県","川崎":"神奈川県",
    "千葉":"千葉県","浦安":"千葉県",
    "さいたま":"埼玉県","大宮":"埼玉県",
    "水戸":"茨城県","宇都宮":"栃木県","高崎":"群馬県",
    "札幌":"北海道","旭川":"北海道","帯広":"北海道","北見":"北海道","函館":"北海道","釧路":"北海道","苫小牧":"北海道",
    "青森":"青森県","盛岡":"岩手県","仙台":"宮城県","宮城":"宮城県","秋田":"秋田県","山形":"山形県",
    "郡山":"福島県","福島":"福島県",
    "新潟":"新潟県","長野":"長野県","松本":"長野県","甲府":"山梨県",
    "富山":"富山県","金沢":"石川県","福井":"福井県",
    "静岡":"静岡県","浜松":"静岡県","清水":"静岡県","清水（静岡）":"静岡県",
    "名古屋":"愛知県","愛知":"愛知県",
    "四日市":"三重県","岐阜":"岐阜県",
    "彦根":"滋賀県","大津（滋賀）":"滋賀県",
    "京都":"京都府",
    "大阪":"大阪府","梅田":"大阪府",
    "神戸":"兵庫県","北九州":"福岡県",
    "奈良":"奈良県","和歌山":"和歌山県",
    "米子":"鳥取県","松江":"島根県","岡山":"岡山県","広島":"広島県","周南":"山口県",
    "高松":"香川県","松山":"愛媛県","高知":"高知県","徳島":"徳島県",
    "福岡":"福岡県","佐賀":"佐賀県","長崎":"長崎県","熊本":"熊本県",
    "大分":"大分県","宮崎":"宮崎県","鹿児島":"鹿児島県","那覇":"沖縄県",
  };

  let allData = [], locView = "city", locChart = null, yrChart = null;
  let sortKey = "shows", sortDir = -1;

  // ─── data fetch ───
  async function fetchData() {
    const cfg = window.SUPABASE_CONFIG;
    if (cfg && cfg.url && cfg.anonKey) {
      const url = `${cfg.url}/rest/v1/timeline_events?select=date,city,venue,tour&type=eq.live&order=date.asc&limit=2000`;
      const res = await fetch(url, {
        headers: { apikey: cfg.anonKey, Authorization: `Bearer ${cfg.anonKey}` },
      });
      if (!res.ok) throw new Error(`Supabase ${res.status}`);
      return res.json();
    }
    const res = await fetch("data/timeline.json", { cache: "no-store" });
    const all = res.ok ? await res.json() : [];
    return all.filter((d) => d.type === "live");
  }

  fetchData()
    .then((data) => {
      allData = data.filter((d) => d.date && d.date.length >= 4);
      buildFilters();
      render();
    })
    .catch((err) => {
      document.getElementById("tourBody").innerHTML =
        `<tr><td colspan="6" class="an-msg" style="color:var(--accent)">データ読み込み失敗: ${err.message}</td></tr>`;
    });

  // ─── filters ───
  function buildFilters() {
    const years = [...new Set(allData.map((d) => d.date.slice(0, 4)))].sort();
    const fY = document.getElementById("fYear");
    years.forEach((y) => fY.append(new Option(y + "年", y)));

    const tours = [...new Set(allData.map((d) => d.tour).filter(Boolean))].sort();
    const fT = document.getElementById("fTour");
    tours.forEach((t) => fT.append(new Option(t.length > 36 ? t.slice(0, 36) + "…" : t, t)));

    const cities = [...new Set(allData.map((d) => d.city).filter(Boolean))].sort();
    const fC = document.getElementById("fCity");
    cities.forEach((c) => fC.append(new Option(c, c)));

    ["fYear", "fTour", "fCity"].forEach((id) =>
      document.getElementById(id).addEventListener("change", render)
    );
  }

  function getFiltered() {
    const yr = document.getElementById("fYear").value;
    const tr = document.getElementById("fTour").value;
    const ci = document.getElementById("fCity").value;
    return allData.filter((d) => {
      if (yr && !d.date.startsWith(yr)) return false;
      if (tr && d.tour !== tr) return false;
      if (ci && d.city !== ci) return false;
      return true;
    });
  }

  function render() {
    const d = getFiltered();
    updateKPIs(d);
    drawLoc(d);
    drawYears(d);
    drawTable(d);
  }

  // ─── KPIs ───
  function updateKPIs(d) {
    document.getElementById("kpiShows").textContent = d.length;
    document.getElementById("kpiTours").textContent = new Set(d.map((x) => x.tour).filter(Boolean)).size;
    document.getElementById("kpiCities").textContent = new Set(d.map((x) => x.city).filter(Boolean)).size;
    const yrs = [...new Set(d.map((x) => x.date.slice(0, 4)))].sort();
    document.getElementById("kpiPeriod").textContent = yrs.length ? yrs[0] + "–" + yrs[yrs.length - 1] : "—";
  }

  // ─── charts ───
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function drawLoc(data) {
    const counts = {};
    data.forEach((d) => {
      const k = d.city ? (locView === "pref" ? (PREF[d.city] || d.city) : d.city) : null;
      if (k) counts[k] = (counts[k] || 0) + 1;
    });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 20);

    const ctx = document.getElementById("locChart").getContext("2d");
    if (locChart) locChart.destroy();

    const acc = css("--accent"), dim = css("--ink-dim"), line = css("--line"), ink = css("--ink");
    locChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: sorted.map((e) => e[0]),
        datasets: [{ data: sorted.map((e) => e[1]), backgroundColor: acc + "88", borderColor: acc, borderWidth: 1, borderRadius: 3 }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + c.raw + "公演" } } },
        scales: {
          x: { grid: { color: line + "66" }, ticks: { color: dim, font: { size: 11 } } },
          y: { grid: { display: false }, ticks: { color: ink, font: { size: 11 }, autoSkip: false } },
        },
      },
    });
    document.getElementById("locTitle").textContent =
      locView === "pref" ? "都道府県別公演数（上位20）" : "都市別公演数（上位20）";
  }

  function drawYears(data) {
    const counts = {};
    data.forEach((d) => { const y = d.date.slice(0, 4); counts[y] = (counts[y] || 0) + 1; });
    const yrs = Object.keys(counts).sort();

    const ctx = document.getElementById("yearChart").getContext("2d");
    if (yrChart) yrChart.destroy();

    const acc = css("--accent"), dim = css("--ink-dim"), line = css("--line");
    yrChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: yrs,
        datasets: [{ data: yrs.map((y) => counts[y]), backgroundColor: acc + "66", borderColor: acc, borderWidth: 1, borderRadius: 3 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + c.raw + "公演" } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: dim, font: { size: 11 }, maxRotation: 45 } },
          y: { grid: { color: line + "66" }, ticks: { color: dim, font: { size: 11 } }, beginAtZero: true },
        },
      },
    });
  }

  // ─── tour table ───
  function drawTable(data) {
    const map = {};
    data.forEach((d) => {
      const k = d.tour || "（ツアー外・単発）";
      if (!map[k]) map[k] = { name: k, shows: 0, cities: new Set(), start: d.date, end: d.date };
      map[k].shows++;
      if (d.city) map[k].cities.add(d.city);
      if (d.date < map[k].start) map[k].start = d.date;
      if (d.date > map[k].end) map[k].end = d.date;
    });

    let rows = Object.values(map).map((r) => ({ ...r, cities: r.cities.size }));
    rows.sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey];
      return typeof va === "number" ? sortDir * (vb - va) : sortDir * String(va).localeCompare(String(vb));
    });

    const maxS = Math.max(...rows.map((r) => r.shows), 1);
    document.getElementById("tourCount").textContent = rows.length + " ツアー";
    const tbody = document.getElementById("tourBody");

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="an-msg">該当なし</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const w = Math.round((r.shows / maxS) * 80);
        return `<tr>
          <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis" title="${r.name}">${r.name}</td>
          <td class="an-mono">${r.shows}</td>
          <td class="an-mono">${r.cities}</td>
          <td class="an-mono an-dim">${r.start.slice(0, 7)}</td>
          <td class="an-mono an-dim">${r.end.slice(0, 7)}</td>
          <td><span class="an-bar" style="width:${w}px"></span></td>
        </tr>`;
      })
      .join("");
  }

  window.sortBy = function (key) {
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = key === "name" ? 1 : -1; }
    ["name", "shows", "cities", "start", "end"].forEach((k) => {
      document.getElementById("s-" + k).textContent = sortKey === k ? (sortDir > 0 ? "↑" : "↓") : "";
      document.querySelector(`th[onclick="sortBy('${k}')"]`).classList.toggle("sorted", sortKey === k);
    });
    drawTable(getFiltered());
  };

  window.setLocView = function (v) {
    locView = v;
    document.getElementById("btnCity").classList.toggle("on", v === "city");
    document.getElementById("btnPref").classList.toggle("on", v === "pref");
    drawLoc(getFiltered());
  };
})();
