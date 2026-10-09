#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dashboardPath = path.resolve(
  process.argv[2] || path.join(here, '..', 'grafana', 'viltkamera-grafana-dashboard-no.json'),
);

const dashboard = JSON.parse(fs.readFileSync(dashboardPath, 'utf8'));
const datasource = { type: 'influxdb', uid: '${DS_WILDLIFE}' };

const cameraQuery = `from(bucket: "Wildlife")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) =>
    r._measurement == "wildlife_camera" and
    contains(value: r._field, set: ["image", "ocr_ok", "temperature_c", "battery_pct"]) and
    contains(value: r.camera, set: ["hc960-01", "hc960-02", "hc960-03", "hc960-04", "hc960-05"])
  )
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> filter(fn: (r) => exists r.image and r.image == 1)
  |> group(columns: ["camera"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
  |> group()
  |> map(fn: (r) => ({
    r with
    camera_name: if r.camera == "hc960-01" then "Kamera 1"
      else if r.camera == "hc960-02" then "Kamera 2"
      else if r.camera == "hc960-03" then "Kamera 3"
      else if r.camera == "hc960-04" then "Kamera 4"
      else "Kamera 5",
    location: if r.camera == "hc960-01" then "Øvre vadeplass"
      else if r.camera == "hc960-02" then "Nest nederste vadested"
      else if r.camera == "hc960-03" then "Bjørneposten"
      else if r.camera == "hc960-04" then "Mellomste vadested"
      else "Stiposten",
    age_hours: float(v: uint(v: now()) - uint(v: r._time)) / 3600000000000.0
  }))
  |> keep(columns: ["camera_name", "location", "temperature_c", "battery_pct", "_time", "age_hours", "ocr_ok"])
  |> sort(columns: ["camera_name"])
  |> yield(name: "Aktive kameraer")`;

const row = {
  collapsed: false,
  gridPos: { h: 1, w: 24, x: 0, y: 0 },
  id: 1,
  panels: [],
  title: 'Aktive viltkameraer',
  type: 'row',
};

const table = {
  datasource,
  description: 'Viser bare kameraer som har minst én bildehendelse i valgt tidsrom. Tabellen fungerer også i offentlige Grafana-dashboards uten malvariabler.',
  fieldConfig: {
    defaults: {
      color: { mode: 'thresholds' },
      mappings: [],
      noValue: '—',
      thresholds: {
        mode: 'absolute',
        steps: [{ color: 'green', value: null }],
      },
    },
    overrides: [
      {
        matcher: { id: 'byName', options: 'camera_name' },
        properties: [
          { id: 'displayName', value: 'Kamera' },
          { id: 'custom.width', value: 110 },
        ],
      },
      {
        matcher: { id: 'byName', options: 'location' },
        properties: [
          { id: 'displayName', value: 'Plassering' },
          { id: 'custom.width', value: 230 },
        ],
      },
      {
        matcher: { id: 'byName', options: 'temperature_c' },
        properties: [
          { id: 'displayName', value: 'Temperatur' },
          { id: 'unit', value: 'celsius' },
          { id: 'decimals', value: 0 },
        ],
      },
      {
        matcher: { id: 'byName', options: 'battery_pct' },
        properties: [
          { id: 'displayName', value: 'Batteri' },
          { id: 'unit', value: 'percent' },
          { id: 'min', value: 0 },
          { id: 'max', value: 100 },
          {
            id: 'thresholds',
            value: {
              mode: 'absolute',
              steps: [
                { color: 'red', value: null },
                { color: 'orange', value: 20 },
                { color: 'green', value: 50 },
              ],
            },
          },
        ],
      },
      {
        matcher: { id: 'byName', options: '_time' },
        properties: [
          { id: 'displayName', value: 'Siste bilde' },
          { id: 'unit', value: 'dateTimeAsLocal' },
          { id: 'custom.width', value: 180 },
        ],
      },
      {
        matcher: { id: 'byName', options: 'age_hours' },
        properties: [
          { id: 'displayName', value: 'Alder' },
          { id: 'unit', value: 'h' },
          { id: 'decimals', value: 1 },
        ],
      },
      {
        matcher: { id: 'byName', options: 'ocr_ok' },
        properties: [
          { id: 'displayName', value: 'OCR-status' },
          {
            id: 'mappings',
            value: [
              {
                options: {
                  0: { color: 'red', index: 1, text: 'Feilet' },
                  1: { color: 'green', index: 0, text: 'OK' },
                },
                type: 'value',
              },
            ],
          },
        ],
      },
    ],
  },
  gridPos: { h: 6, w: 24, x: 0, y: 1 },
  id: 2,
  options: {
    cellHeight: 'sm',
    footer: {
      countRows: false,
      fields: '',
      reducer: ['sum'],
      show: false,
    },
    showHeader: true,
    sortBy: [{ desc: false, displayName: 'Kamera' }],
  },
  pluginVersion: '11.0.0',
  targets: [{ datasource, query: cameraQuery, refId: 'A' }],
  title: 'Kameraer med aktivitet i valgt tidsrom',
  type: 'table',
};

const temperatureHistory = dashboard.panels.find((panel) => panel.id === 32);
const imageHistory = dashboard.panels.find((panel) => panel.id === 34);
const elkPanels = dashboard.panels.filter((panel) => panel.id >= 35);

if (!temperatureHistory || !imageHistory || elkPanels.length === 0) {
  throw new Error('Fant ikke forventede historikk- eller elgpaneler i dashboardet');
}

const elkPanelY = new Map([
  [35, 7],
  [36, 8],
  [37, 8],
  [38, 8],
  [39, 8],
  [40, 12],
  [41, 12],
  [42, 20],
  [43, 20],
  [44, 28],
]);

for (const panel of elkPanels) {
  const y = elkPanelY.get(panel.id);
  if (y === undefined) {
    throw new Error(`Mangler plassering for elgpanel ${panel.id}`);
  }
  panel.gridPos.y = y;
}

const historyRow = {
  collapsed: false,
  gridPos: { h: 1, w: 24, x: 0, y: 36 },
  id: 26,
  panels: [],
  title: 'Aktivitet og historikk',
  type: 'row',
};

temperatureHistory.gridPos = { h: 8, w: 24, x: 0, y: 37 };
imageHistory.gridPos = { h: 8, w: 24, x: 0, y: 45 };

dashboard.panels = [
  row,
  table,
  ...elkPanels,
  historyRow,
  temperatureHistory,
  imageHistory,
];
dashboard.description = 'Offentlig-kompatibel oversikt med datadrevet kameratabell, temperatur- og bildehistorikk og elgjaktdata. Inaktive kameraer vises ikke som egne rader.';
dashboard.version = 1;

fs.writeFileSync(dashboardPath, `${JSON.stringify(dashboard, null, 2)}\n`);
console.log(`Oppdaterte ${dashboardPath}`);

