#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dashboardPath = path.resolve(
  process.argv[2] || path.join(here, '..', 'grafana', 'viltkamera-grafana-dashboard-no.json'),
);
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, 'utf8'));
const activeHuntingGround = `activeJaktfelt = from(bucket: "Wildlife")
  |> range(start: 1970-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_config" and r.scope == "active" and r._field == "jaktfelt_id")
  |> last()
  |> findRecord(fn: (key) => true, idx: 0)`;

let changed = 0;
for (const panel of dashboard.panels || []) {
  if (panel.id === 35 && panel.title !== 'Elgjakt – aktivt jaktfelt') {
    panel.title = 'Elgjakt – aktivt jaktfelt';
    changed += 1;
  }
  for (const target of panel.targets || []) {
    if (!target.query?.includes('r.jaktfelt_id == "1840J0096"')) continue;
    const query = target.query.replaceAll(
      'r.jaktfelt_id == "1840J0096"',
      'r.jaktfelt_id == activeJaktfelt._value',
    );
    const imports = query.match(/^(?:import [^\n]+\n)+\n?/);
    target.query = imports
      ? `${imports[0]}${activeHuntingGround}\n\n${query.slice(imports[0].length)}`
      : `${activeHuntingGround}\n\n${query}`;
    changed += 1;
  }
}

fs.writeFileSync(dashboardPath, `${JSON.stringify(dashboard, null, 2)}\n`);
console.log(`Oppdaterte ${dashboardPath}: ${changed} dynamiske jaktfeltendringer.`);
