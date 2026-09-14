// Evaluator instance 1: update ONLY the four permitted fields on group A rows.
// Identity/specification fields (id, category, story, group, cluster,
// acceptance_criterion, description, steps, verification) are never touched.
const fs = require("fs");
const path = "C:/Users/rosuo/WORK/ai-native-capstone-truelend/features.json";
const raw = fs.readFileSync(path, "utf8");
const arr = JSON.parse(raw);

const TS = "2026-09-14T11:52:00Z";
const GROUP_A = ["F001", "F002", "F003", "F004", "F005", "F009", "F010", "F011", "F070", "F071", "F072", "F073"];

// Every group-A acceptance criterion was independently verified and passed.
// The gate's overall FAIL is a security finding (HIGH-1, /metrics metric
// forgery) that no acceptance criterion covers -- see MED-3. It is recorded in
// specs/reviews/evaluator-evidence.json, not on an AC row, because writing it
// onto an unrelated AC row would misreport that criterion.
const RESULT = Object.fromEntries(GROUP_A.map((id) => [id, { passes: true, failure_reason: null, failure_layer: null }]));

const ALLOWED = new Set(["passes", "last_evaluated", "failure_reason", "failure_layer"]);
let changed = 0;
const before = new Map();

for (const row of arr) {
  if (!RESULT[row.id]) continue;
  before.set(row.id, JSON.stringify(row));
  const r = RESULT[row.id];
  row.passes = r.passes;
  row.last_evaluated = TS;
  row.failure_reason = r.failure_reason;
  row.failure_layer = r.failure_layer;
  changed++;
}

// Guard: assert nothing outside the four permitted fields moved.
for (const row of arr) {
  if (!before.has(row.id)) continue;
  const old = JSON.parse(before.get(row.id));
  for (const k of Object.keys(old)) {
    if (ALLOWED.has(k)) continue;
    if (JSON.stringify(old[k]) !== JSON.stringify(row[k])) {
      throw new Error(`ILLEGAL MUTATION of identity field ${row.id}.${k}`);
    }
  }
}

fs.writeFileSync(path, JSON.stringify(arr, null, 2) + "\n", "utf8");
console.log(`updated ${changed} group-A rows (expected ${GROUP_A.length})`);
console.log("total features preserved: " + arr.length);
