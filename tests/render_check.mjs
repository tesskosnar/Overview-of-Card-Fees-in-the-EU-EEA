import { JSDOM } from "jsdom";

const url = process.argv[2] || "http://localhost:8940/index.html";

const dom = await JSDOM.fromURL(url, {
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
  beforeParse(window) {
    window.fetch = function (input, init) {
      var resolved = new URL(input, window.location.href).href;
      return fetch(resolved, init);
    };
  },
});

await new Promise((r) => setTimeout(r, 1000));
await new Promise((r) => setTimeout(r, 1000));

const doc = dom.window.document;
let failures = 0;
function check(label, cond) {
  console.log((cond ? "PASS " : "FAIL ") + label);
  if (!cond) failures++;
}

const appHTML = doc.getElementById("app").innerHTML;
check("app rendered content", appHTML.length > 300);
check("no JS error state shown", !appHTML.toLowerCase().includes("error"));

check("only ONE tab exists (Interchange fees)", doc.querySelectorAll(".tab").length === 1);
check("no 'Scheme & processing' tab", ![...doc.querySelectorAll(".tab")].some(t => t.textContent.includes("Scheme")));
check("no 'Merchant service charge' tab", ![...doc.querySelectorAll(".tab")].some(t => t.textContent.includes("Merchant service")));

check("no estimate-card rendered", !doc.querySelector(".estimate-card"));
check("no 'Odhadovaný reálný poplatek' text anywhere", !appHTML.includes("Odhadovaný"));

check("no Media column header in table", ![...doc.querySelectorAll("th")].some(th => th.textContent.trim() === "Media"));
check("no media-badge elements", doc.querySelectorAll(".media-badge").length === 0);
check("no 'Media a další veřejné zdroje' section", !appHTML.includes("Media a další"));

check("interchange table still rendered", !!doc.querySelector(".table-wrap table"));
check("trend section still rendered", !!doc.getElementById("trendHost"));

check("map has 30 real country SVG paths (not tile buttons)", doc.querySelectorAll(".map-country").length === 30);
check("no leftover tile-grid buttons", doc.querySelectorAll(".map-tile").length === 0);
check("map detail panel shows Germany by default", doc.getElementById("mapDetail").textContent.includes("Germany") || doc.getElementById("mapDetail").textContent.includes("Německo"));
const czPath = [...doc.querySelectorAll(".map-country")].find(t => t.dataset.iso === "CZ");
if (czPath) {
  czPath.dispatchEvent(new dom.window.MouseEvent('click', {bubbles:true}));
  const detailText = doc.getElementById("mapDetail").textContent;
  check("clicking a country path updates the detail panel", detailText.includes("Czech") || detailText.includes("Česko"));
} else {
  check("CZ country path exists to click", false);
}
check("scheme dots present for countries with domestic schemes", doc.querySelectorAll(".map-scheme-dot").length > 0);

check("region buttons present (not a dropdown)", doc.querySelectorAll(".region-btn").length === 5);
check("no leftover region dropdown", !doc.getElementById("regionSelect"));

check("search input present", !!doc.getElementById("searchInput"));

const commBtn = [...doc.querySelectorAll(".seg-btn")].find(b => b.dataset.cat === "commercial");
if (commBtn) commBtn.dispatchEvent(new dom.window.MouseEvent('click', {bubbles:true}));
await new Promise((r) => setTimeout(r, 800));
check("trend chart shows all 3 real history points under Commercial (2015, 2017, current)", (() => {
  const svgContent = doc.getElementById("trendHost").innerHTML;
  return ['2015','2017'].every(y => svgContent.includes(y));
})());

console.log(failures === 0 ? "\nALL CHECKS PASSED" : "\n" + failures + " CHECK(S) FAILED");
process.exitCode = failures === 0 ? 0 : 1;
