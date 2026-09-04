'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const extension = require('./server.js');

const {normalizeMediaKey, keyFromAbsolutePath, addKeyword, removeKeyword, serializeStore} = extension._test;

assert.equal(normalizeMediaKey('/hc960-01/photo.JPG'), 'hc960-01/photo.JPG');
assert.equal(normalizeMediaKey('hc960-01\\photo.JPG'), 'hc960-01/photo.JPG');
assert.throws(() => normalizeMediaKey('../outside.JPG'));
assert.throws(() => normalizeMediaKey(''));

const imageRoot = path.resolve('photos');
assert.equal(
  keyFromAbsolutePath(path.join(imageRoot, 'hc960-03', 'photo.JPG'), imageRoot),
  'hc960-03/photo.JPG'
);
assert.equal(keyFromAbsolutePath(path.resolve('outside', 'photo.JPG'), imageRoot), null);

const metadata = {keywords: ['existing']};
addKeyword(metadata);
addKeyword(metadata);
assert.deepEqual(metadata.keywords, ['existing', 'pg-album:bekreftede-observasjoner']);
removeKeyword(metadata);
assert.deepEqual(metadata.keywords, ['existing']);

const serialized = serializeStore({
  version: 1,
  albumName: 'Bekreftede observasjoner',
  keyword: 'pg-album:bekreftede-observasjoner',
  updatedAt: '2026-08-26T00:00:00.000Z',
  photos: {
    'hc960-05/z.JPG': {verifiedAt: '2026-08-26T00:00:00.000Z'},
    'hc960-01/a.JPG': {verifiedAt: '2026-08-26T00:00:00.000Z'}
  }
});
assert.ok(serialized.indexOf('hc960-01/a.JPG') < serialized.indexOf('hc960-05/z.JPG'));

console.log('All verified-sightings extension tests passed.');
