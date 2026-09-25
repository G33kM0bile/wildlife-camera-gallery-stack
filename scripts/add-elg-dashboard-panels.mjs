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

const target = (query) => [{ datasource, query, refId: 'A' }];

const stat = ({ id, title, description, x, query, unit = 'short', noValue = '0' }) => ({
  datasource,
  description,
  fieldConfig: {
    defaults: {
      color: { mode: 'thresholds' },
      mappings: [],
      noValue,
      thresholds: {
        mode: 'absolute',
        steps: [
          { color: 'dark-blue', value: null },
          { color: 'green', value: 1 },
        ],
      },
      unit,
    },
    overrides: [],
  },
  gridPos: { h: 4, w: 6, x, y: 49 },
  id,
  options: {
    colorMode: 'background',
    graphMode: 'none',
    justifyMode: 'center',
    orientation: 'auto',
    reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false },
    textMode: 'value',
    wideLayout: true,
  },
  pluginVersion: '11.0.0',
  targets: target(query),
  title,
  type: 'stat',
});

const timeseriesDefaults = (unit = 'short', drawStyle = 'line') => ({
  color: { mode: 'palette-classic' },
  custom: {
    axisCenteredZero: false,
    axisColorMode: 'text',
    axisLabel: '',
    axisPlacement: 'auto',
    barAlignment: 0,
    drawStyle,
    fillOpacity: drawStyle === 'bars' ? 45 : 18,
    gradientMode: 'opacity',
    hideFrom: { legend: false, tooltip: false, viz: false },
    insertNulls: false,
    lineInterpolation: 'linear',
    lineWidth: 2,
    pointSize: 5,
    scaleDistribution: { type: 'linear' },
    showPoints: drawStyle === 'bars' ? 'never' : 'always',
    spanNulls: false,
    stacking: { group: 'A', mode: 'none' },
    thresholdsStyle: { mode: 'off' },
  },
  mappings: [],
  thresholds: { mode: 'absolute', steps: [{ color: 'green', value: null }] },
  unit,
});

const timeseries = ({ id, title, description, x, y, w, query, unit, drawStyle }) => ({
  datasource,
  description,
  fieldConfig: { defaults: timeseriesDefaults(unit, drawStyle), overrides: [] },
  gridPos: { h: 8, w, x, y },
  id,
  options: {
    legend: {
      calcs: ['lastNotNull'],
      displayMode: 'list',
      placement: 'bottom',
      showLegend: true,
    },
    tooltip: { hideZeros: false, mode: 'multi', sort: 'desc' },
  },
  pluginVersion: '11.0.0',
  targets: target(query),
  title,
  type: 'timeseries',
});

const qCurrentCount = `import "date"

from(bucket: "Wildlife")
  |> range(start: date.truncate(t: now(), unit: 1y), stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "felling")
  |> sum()`;

const qAverageWeight = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "slaktevekt")
  |> mean()`;

const qLatestWeight = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "slaktevekt")
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)`;

const qHistoricalCount = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "felling")
  |> sum()`;

const qCumulative = `import "date"

from(bucket: "Wildlife")
  |> range(start: date.truncate(t: now(), unit: 1y), stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "felling")
  |> group(columns: ["jaktfelt_id"])
  |> sort(columns: ["_time"])
  |> cumulativeSum(columns: ["_value"])
  |> yield(name: "Felt")`;

const qDistribution = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and contains(value: r._field, set: ["felling", "kategori_skutt"]))
  |> pivot(rowKey: ["_time", "storvilt_id"], columnKey: ["_field"], valueColumn: "_value")
  |> group(columns: ["kategori_skutt"])
  |> sum(column: "felling")
  |> rename(columns: {felling: "_value"})
  |> keep(columns: ["kategori_skutt", "_value"])
  |> group()
  |> yield(name: "Fordeling")`;

const qYearly = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and r._field == "felling")
  |> aggregateWindow(every: 1y, fn: sum, createEmpty: false, timeSrc: "_start")
  |> yield(name: "Felte elg")`;

const qWeightByCategory = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and contains(value: r._field, set: ["kategori_skutt", "slaktevekt"]))
  |> pivot(rowKey: ["_time", "storvilt_id"], columnKey: ["_field"], valueColumn: "_value")
  |> group(columns: ["kategori_skutt"])
  |> mean(column: "slaktevekt")
  |> rename(columns: {slaktevekt: "_value"})
  |> keep(columns: ["kategori_skutt", "_value"])
  |> group()
  |> yield(name: "Snittvekt")`;

const qRecent = `from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) => r._measurement == "elg_felling" and r.jaktfelt_id == "1840J0096" and contains(value: r._field, set: ["felling", "kategori", "kategori_skutt", "slaktevekt"]))
  |> pivot(rowKey: ["_time", "storvilt_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 20)
  |> keep(columns: ["_time", "storvilt_id", "kategori", "kategori_skutt", "slaktevekt"])
  |> yield(name: "Siste felte dyr")`;

const elgPanels = [
  {
    collapsed: false,
    gridPos: { h: 1, w: 24, x: 0, y: 48 },
    id: 35,
    panels: [],
    title: 'Elgjakt – Storjord Øst',
    type: 'row',
  },
  stat({
    id: 36,
    title: 'Felt hittil i år',
    description: 'Unike registrerte elgfellinger i inneværende kalenderår.',
    x: 0,
    query: qCurrentCount,
  }),
  stat({
    id: 37,
    title: 'Gjennomsnittlig slaktevekt',
    description: 'Gjennomsnitt for alle gyldige positive slaktevekter i historikken.',
    x: 6,
    query: qAverageWeight,
    unit: 'kg',
    noValue: 'Ingen vektdata',
  }),
  stat({
    id: 38,
    title: 'Siste registrerte slaktevekt',
    description: 'Slaktevekten til den nyeste fellingen som har en gyldig vekt.',
    x: 12,
    query: qLatestWeight,
    unit: 'kg',
    noValue: 'Ingen vektdata',
  }),
  stat({
    id: 39,
    title: 'Fellinger i historikken',
    description: 'Totalt antall unike importerte fellinger fra 2019 og fremover.',
    x: 18,
    query: qHistoricalCount,
  }),
  timeseries({
    id: 40,
    title: 'Fellinger gjennom årets jakt',
    description: 'Kumulativt antall fellinger i inneværende kalenderår.',
    x: 0,
    y: 53,
    w: 12,
    query: qCumulative,
    unit: 'short',
    drawStyle: 'line',
  }),
  {
    datasource,
    description: 'Historisk fordeling etter Statskogs detaljerte Kategoriskutt-felt.',
    fieldConfig: {
      defaults: {
        color: { mode: 'palette-classic' },
        mappings: [],
        unit: 'short',
      },
      overrides: [],
    },
    gridPos: { h: 8, w: 12, x: 12, y: 53 },
    id: 41,
    options: {
      displayLabels: ['name', 'percent', 'value'],
      legend: { displayMode: 'table', placement: 'right', showLegend: true, values: ['value'] },
      pieType: 'donut',
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: true },
      tooltip: { hideZeros: false, mode: 'single', sort: 'none' },
    },
    pluginVersion: '11.0.0',
    targets: target(qDistribution),
    title: 'Fordeling',
    type: 'piechart',
  },
  timeseries({
    id: 42,
    title: 'Felte elg per år',
    description: 'Historisk antall fellinger gruppert per kalenderår.',
    x: 0,
    y: 61,
    w: 12,
    query: qYearly,
    unit: 'short',
    drawStyle: 'bars',
  }),
  {
    datasource,
    description: 'Gjennomsnittlig gyldig slaktevekt per detaljert kategori.',
    fieldConfig: {
      defaults: {
        color: { mode: 'palette-classic' },
        custom: { axisLabel: 'kg', axisPlacement: 'auto', fillOpacity: 65, lineWidth: 1 },
        mappings: [],
        unit: 'kg',
      },
      overrides: [],
    },
    gridPos: { h: 8, w: 12, x: 12, y: 61 },
    id: 43,
    options: {
      barRadius: 0,
      barWidth: 0.75,
      fullHighlight: false,
      groupWidth: 0.7,
      legend: { calcs: [], displayMode: 'list', placement: 'bottom', showLegend: false },
      orientation: 'horizontal',
      showValue: 'always',
      stacking: 'none',
      tooltip: { hideZeros: false, mode: 'single', sort: 'none' },
      xTickLabelRotation: 0,
      xTickLabelSpacing: 0,
    },
    pluginVersion: '11.0.0',
    targets: target(qWeightByCategory),
    title: 'Gjennomsnittlig slaktevekt per kategori',
    type: 'barchart',
  },
  {
    datasource,
    description: 'De 20 nyeste registrerte elgfellingene. Tom vekt betyr at Statskog ikke har en gyldig positiv slaktevekt.',
    fieldConfig: {
      defaults: { color: { mode: 'thresholds' }, mappings: [], thresholds: { mode: 'absolute', steps: [{ color: 'green', value: null }] } },
      overrides: [
        { matcher: { id: 'byName', options: '_time' }, properties: [{ id: 'displayName', value: 'Dato' }, { id: 'unit', value: 'dateTimeAsLocal' }] },
        { matcher: { id: 'byName', options: 'storvilt_id' }, properties: [{ id: 'displayName', value: 'Statskog-ID' }] },
        { matcher: { id: 'byName', options: 'kategori' }, properties: [{ id: 'displayName', value: 'Kategori' }] },
        { matcher: { id: 'byName', options: 'kategori_skutt' }, properties: [{ id: 'displayName', value: 'Detaljert kategori' }] },
        { matcher: { id: 'byName', options: 'slaktevekt' }, properties: [{ id: 'displayName', value: 'Slaktevekt' }, { id: 'unit', value: 'kg' }] },
      ],
    },
    gridPos: { h: 8, w: 24, x: 0, y: 69 },
    id: 44,
    options: {
      cellHeight: 'sm',
      footer: { countRows: false, fields: '', reducer: ['sum'], show: false },
      showHeader: true,
      sortBy: [{ desc: true, displayName: 'Dato' }],
    },
    pluginVersion: '11.0.0',
    targets: target(qRecent),
    title: 'Siste felte dyr',
    type: 'table',
  },
];

const managedIds = new Set(elgPanels.map((panel) => panel.id));
dashboard.panels = dashboard.panels.filter((panel) => !managedIds.has(panel.id));
dashboard.panels.push(...elgPanels);
dashboard.version = Math.max(Number(dashboard.version || 0), 3);
dashboard.time = { from: 'now-48h', to: 'now' };

fs.writeFileSync(dashboardPath, JSON.stringify(dashboard, null, 2) + '\n', 'utf8');
console.log(`Updated ${dashboardPath} with ${elgPanels.length} managed panels.`);
