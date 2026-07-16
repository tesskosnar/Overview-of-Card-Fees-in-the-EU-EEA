import { JSDOM } from "jsdom";

const url = process.argv[2] || "http://localhost:8934/index.html";
const dom = await JSDOM.fromURL(url, {
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
  beforeParse(window) {
    window.fetch = (input, init) => fetch(new URL(input, window.location.href).href, init);
  },
});
await new Promise((resolve) => setTimeout(resolve, 1800));
const doc = dom.window.document;
let failures = 0;
function check(label, condition) {
  console.log((condition ? "PASS " : "FAIL ") + label);
  if (!condition) failures += 1;
}

check("dashboard rendered", doc.getElementById("app").innerHTML.length > 1000);
check("no loading error", !doc.getElementById("app").textContent.includes("nepodařilo načíst"));
check("Arial is configured", doc.documentElement.innerHTML.includes("Arial,Helvetica,sans-serif"));
check("three fee-layer tabs exist", doc.querySelectorAll(".tab").length === 3);
check("estimated real fee card exists", doc.body.textContent.includes("Odhadovaný reálný poplatek"));
check("CEE quick filter exists", !!doc.getElementById("ceeBtn"));
check("trend host exists", !!doc.getElementById("trendHost"));
check("Germany seed row exists", [...doc.querySelectorAll("tbody tr")].some(r => r.textContent.includes("Germany")));

const schemeTab = doc.querySelector('[data-layer="scheme_processing"]');
schemeTab.dispatchEvent(new dom.window.Event("click", { bubbles: true }));
await new Promise((resolve) => setTimeout(resolve, 250));
check("scheme layer renders", doc.body.textContent.includes("Veřejně dohledané scheme a processing fees"));
check("empty media state is handled", doc.body.textContent.includes("zatím nebyl nalezen veřejný zdroj"));

const cee = doc.getElementById("ceeBtn");
cee.dispatchEvent(new dom.window.Event("click", { bubbles: true }));
await new Promise((resolve) => setTimeout(resolve, 150));
const select = doc.getElementById("regionSelect");
check("CEE filter updates region select", select && select.value === "CEE");

console.log(failures ? `\n${failures} check(s) failed` : "\nALL CHECKS PASSED");
process.exitCode = failures ? 1 : 0;
