// Evaluator instance 1: assert 100% of log lines parse as JSON and carry the
// expected request_id. Usage: node logcheck.js <logfile> [expected_request_id]
const fs = require("fs");
const file = process.argv[2];
const expected = process.argv[3] || null;
const lines = fs.readFileSync(file, "utf8").split("\n").filter((l) => l.length > 0);

let parsed = 0;
const notJson = [];
const ids = new Map();
const missingId = [];

lines.forEach((l, i) => {
  let o;
  try {
    o = JSON.parse(l);
  } catch (e) {
    notJson.push(i + 1 + ": " + l.slice(0, 120));
    return;
  }
  parsed++;
  const rid = o.request_id;
  if (rid === undefined) missingId.push(i + 1);
  ids.set(String(rid), (ids.get(String(rid)) || 0) + 1);
});

console.log("file: " + file);
console.log("total non-empty lines (DENOMINATOR): " + lines.length);
console.log("parsed as JSON: " + parsed + "  (" + (lines.length ? ((100 * parsed) / lines.length).toFixed(1) : "n/a") + "%)");
console.log("lines NOT parsing as JSON: " + notJson.length);
notJson.forEach((n) => console.log("  " + n));
console.log("lines with no request_id key at all: " + missingId.length);
console.log("distinct request_id values -> count:");
[...ids.entries()].forEach(([k, v]) => console.log("  [" + k + "] -> " + v));

if (expected) {
  const wrong = lines.filter((l) => {
    try {
      return JSON.parse(l).request_id !== expected;
    } catch (e) {
      return true;
    }
  });
  console.log("expected request_id = [" + expected + "]");
  console.log("lines NOT carrying it: " + wrong.length);
  console.log("VERDICT: " + (lines.length > 0 && wrong.length === 0 ? "PASS" : "FAIL"));
}
