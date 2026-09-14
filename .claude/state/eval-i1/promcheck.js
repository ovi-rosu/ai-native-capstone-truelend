// Minimal Prometheus text-exposition well-formedness check.
// A data line must be: <name>{<lbl>="<v>",...} <number>
// We check structurally without a fragile regex: balanced quotes, a single
// space-separated trailing number, and a closing brace before it.
const fs = require("fs");
const txt = fs.readFileSync(process.argv[2], "utf8");
const lines = txt.split("\n");
const bad = [];
let data = 0;

for (let i = 0; i < lines.length; i++) {
  const l = lines[i];
  if (!l.trim() || l.startsWith("#")) continue;
  data++;
  const reasons = [];
  // count quotes (none should be escaped in this producer's output)
  const quotes = (l.match(/"/g) || []).length;
  if (quotes % 2 !== 0) reasons.push("odd number of quotes (" + quotes + ")");
  const braceOpen = (l.match(/\{/g) || []).length;
  const braceClose = (l.match(/\}/g) || []).length;
  if (braceOpen !== braceClose) reasons.push("unbalanced braces");
  const tail = l.split(" ").pop();
  if (!/^[-+0-9.eE]+$/.test(tail)) reasons.push("trailing token not a number: " + JSON.stringify(tail));
  if (braceOpen > 0 && !/\}\s[-+0-9.eE]+$/.test(l)) reasons.push("no '} <value>' terminator");
  if (reasons.length) bad.push("line " + (i + 1) + ": " + JSON.stringify(l) + " -> " + reasons.join("; "));
}

console.log("non-comment data lines: " + data);
console.log("malformed lines: " + bad.length);
bad.forEach((b) => console.log("  " + b));
