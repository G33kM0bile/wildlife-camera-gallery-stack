"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports._test = exports.cleanUp = exports.init = void 0;
const fs = require("fs");
const path = require("path");
const UserDTO_1 = require("./node_modules/pigallery2-extension-kit/lib/common/entities/UserDTO");
const SearchQueryDTO_1 = require("./node_modules/pigallery2-extension-kit/lib/common/entities/SearchQueryDTO");
const ALBUM_NAME = 'Bekreftede observasjoner';
const ALBUM_KEYWORD = 'pg-album:bekreftede-observasjoner';
const STORE_VERSION = 1;
const STORE_FILE = path.join(__dirname, 'verified-sightings.json');
let store;
let pendingWrite = Promise.resolve();
function emptyStore() {
    return {
        version: STORE_VERSION,
        albumName: ALBUM_NAME,
        keyword: ALBUM_KEYWORD,
        updatedAt: new Date(0).toISOString(),
        photos: {}
    };
}
function normalizeMediaKey(rawPath) {
    if (typeof rawPath !== 'string' || rawPath.trim() === '') {
        throw new Error('Mangler filsti for bildet.');
    }
    const slashPath = rawPath.replace(/\\/g, '/').replace(/^\/+/, '');
    const normalized = path.posix.normalize(slashPath);
    if (normalized === '.' ||
        normalized === '..' ||
        normalized.startsWith('../') ||
        path.posix.isAbsolute(normalized)) {
        throw new Error(`Ugyldig bildesti: ${rawPath}`);
    }
    return normalized;
}
function keyFromAbsolutePath(absolutePath, imageFolder) {
    const relative = path.relative(imageFolder, absolutePath);
    if (relative === '' ||
        path.isAbsolute(relative) ||
        relative === '..' ||
        relative.startsWith(`..${path.sep}`)) {
        return null;
    }
    return normalizeMediaKey(relative);
}
async function loadStore() {
    try {
        const raw = await fs.promises.readFile(STORE_FILE, 'utf8');
        const parsed = JSON.parse(raw);
        if (parsed.version !== STORE_VERSION || !parsed.photos || typeof parsed.photos !== 'object') {
            throw new Error('ukjent eller ugyldig format');
        }
        const photos = {};
        for (const [rawKey, value] of Object.entries(parsed.photos)) {
            const key = normalizeMediaKey(rawKey);
            if (!value || typeof value.verifiedAt !== 'string') {
                throw new Error(`ugyldig oppføring for ${key}`);
            }
            photos[key] = {
                verifiedAt: value.verifiedAt,
                ...(typeof value.verifiedBy === 'string' ? { verifiedBy: value.verifiedBy } : {})
            };
        }
        return {
            version: STORE_VERSION,
            albumName: ALBUM_NAME,
            keyword: ALBUM_KEYWORD,
            updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : new Date(0).toISOString(),
            photos
        };
    }
    catch (error) {
        const err = error;
        if (err.code === 'ENOENT') {
            return emptyStore();
        }
        throw new Error(`Kan ikke lese ${STORE_FILE}: ${err.message}`);
    }
}
function serializeStore(snapshot) {
    const photos = Object.fromEntries(Object.entries(snapshot.photos).sort(([a], [b]) => a.localeCompare(b)));
    return JSON.stringify({ ...snapshot, photos }, null, 2) + '\n';
}
function queueStoreWrite() {
    store.updatedAt = new Date().toISOString();
    const snapshot = serializeStore(store);
    const tempFile = `${STORE_FILE}.tmp-${process.pid}`;
    const writeSnapshot = async () => {
        await fs.promises.writeFile(tempFile, snapshot, { encoding: 'utf8', mode: 0o600 });
        await fs.promises.rename(tempFile, STORE_FILE);
    };
    pendingWrite = pendingWrite.then(writeSnapshot, writeSnapshot);
    return pendingWrite;
}
function addKeyword(metadata) {
    metadata.keywords = metadata.keywords || [];
    if (!metadata.keywords.includes(ALBUM_KEYWORD)) {
        metadata.keywords.push(ALBUM_KEYWORD);
    }
}
function removeKeyword(metadata) {
    metadata.keywords = (metadata.keywords || []).filter(keyword => keyword !== ALBUM_KEYWORD);
}
async function ensureAlbum(extension) {
    await extension._app.objectManagers.AlbumManager.addIfNotExistSavedSearch(ALBUM_NAME, {
        type: SearchQueryDTO_1.SearchQueryTypes.keyword,
        value: ALBUM_KEYWORD,
        matchType: SearchQueryDTO_1.TextSearchQueryMatchTypes.exact_match
    }, false);
}
function verifiedEntryFor(user) {
    return {
        verifiedAt: new Date().toISOString(),
        ...(user?.name ? { verifiedBy: user.name } : {})
    };
}
const verifiedIcon = {
    viewBox: '0 0 512 512',
    items: '<path d="M256 48a208 208 0 1 0 0 416 208 208 0 0 0 0-416zm97 152L238 330a24 24 0 0 1-35 1l-57-57a24 24 0 1 1 34-34l39 39 98-111a24 24 0 1 1 36 32z"/>'
};
const removeIcon = {
    viewBox: '0 0 512 512',
    items: '<path d="M256 48a208 208 0 1 0 0 416 208 208 0 0 0 0-416zm74 282a24 24 0 0 1-34 0l-40-40-40 40a24 24 0 1 1-34-34l40-40-40-40a24 24 0 1 1 34-34l40 40 40-40a24 24 0 1 1 34 34l-40 40 40 40a24 24 0 0 1 0 34z"/>'
};
const init = async (extension) => {
    store = await loadStore();
    await queueStoreWrite();
    await ensureAlbum(extension);
    extension.Logger.info(`Bekreftede observasjoner startet med ${Object.keys(store.photos).length} markerte bilder. Register: ${STORE_FILE}`);
    extension.events.gallery.MetadataLoader.loadPhotoMetadata.after(async (data) => {
        const key = keyFromAbsolutePath(data.input[0], extension.paths.ImageFolder);
        if (key && store.photos[key]) {
            addKeyword(data.output);
        }
        return data.output;
    });
    extension.ui.addMediaButton({
        name: 'Bekreftet observasjon',
        svgIcon: verifiedIcon,
        minUserRole: UserDTO_1.UserRoles.User,
        apiPath: 'verify',
        reloadContent: true,
        skipVideos: true,
        alwaysVisible: true
    }, async (_params, body, user, media, repository) => {
        const key = normalizeMediaKey(body.media);
        store.photos[key] = store.photos[key] || verifiedEntryFor(user);
        await queueStoreWrite();
        addKeyword(media.metadata);
        await repository.save(media);
        await ensureAlbum(extension);
        extension.Logger.info(`Bekreftet observasjon: ${key}`);
    });
    extension.ui.addMediaButton({
        name: 'Fjern bekreftelse',
        svgIcon: removeIcon,
        minUserRole: UserDTO_1.UserRoles.User,
        apiPath: 'unverify',
        reloadContent: true,
        skipVideos: true,
        popup: {
            header: 'Fjern bekreftet observasjon',
            body: 'Vil du fjerne dette bildet fra albumet «Bekreftede observasjoner»?',
            buttonString: 'Fjern'
        }
    }, async (_params, body, _user, media, repository) => {
        const key = normalizeMediaKey(body.media);
        delete store.photos[key];
        await queueStoreWrite();
        removeKeyword(media.metadata);
        await repository.save(media);
        extension.Logger.info(`Fjernet bekreftet observasjon: ${key}`);
    });
};
exports.init = init;
const cleanUp = async () => {
    await pendingWrite;
};
exports.cleanUp = cleanUp;
exports._test = {
    normalizeMediaKey,
    keyFromAbsolutePath,
    addKeyword,
    removeKeyword,
    serializeStore
};
//# sourceMappingURL=server.js.map