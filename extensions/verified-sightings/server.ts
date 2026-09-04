import * as fs from 'fs';
import * as path from 'path';

import type {IExtensionObject} from './node_modules/pigallery2-extension-kit';
import type {PhotoMetadata} from './node_modules/pigallery2-extension-kit/lib/common/entities/PhotoDTO';
import {UserRoles} from './node_modules/pigallery2-extension-kit/lib/common/entities/UserDTO';
import type {UserDTO} from './node_modules/pigallery2-extension-kit/lib/common/entities/UserDTO';
import type {MediaEntity} from './node_modules/pigallery2-extension-kit/lib/backend/model/database/enitites/MediaEntity';
import {
  SearchQueryTypes,
  TextSearchQueryMatchTypes
} from './node_modules/pigallery2-extension-kit/lib/common/entities/SearchQueryDTO';
import type {TextSearch} from './node_modules/pigallery2-extension-kit/lib/common/entities/SearchQueryDTO';
import type {IMediaRequestBody} from './node_modules/pigallery2-extension-kit/lib/backend/model/extension/IExtension';
import type {Repository} from 'typeorm';

type ParamsDictionary = Record<string, string>;

const ALBUM_NAME = 'Bekreftede observasjoner';
const ALBUM_KEYWORD = 'pg-album:bekreftede-observasjoner';
const STORE_VERSION = 1;
const STORE_FILE = path.join(__dirname, 'verified-sightings.json');

interface VerifiedEntry {
  verifiedAt: string;
  verifiedBy?: string;
}

interface VerifiedStore {
  version: number;
  albumName: string;
  keyword: string;
  updatedAt: string;
  photos: Record<string, VerifiedEntry>;
}

let store: VerifiedStore;
let pendingWrite: Promise<void> = Promise.resolve();

function emptyStore(): VerifiedStore {
  return {
    version: STORE_VERSION,
    albumName: ALBUM_NAME,
    keyword: ALBUM_KEYWORD,
    updatedAt: new Date(0).toISOString(),
    photos: {}
  };
}

function normalizeMediaKey(rawPath: string): string {
  if (typeof rawPath !== 'string' || rawPath.trim() === '') {
    throw new Error('Mangler filsti for bildet.');
  }

  const slashPath = rawPath.replace(/\\/g, '/').replace(/^\/+/, '');
  const normalized = path.posix.normalize(slashPath);

  if (
    normalized === '.' ||
    normalized === '..' ||
    normalized.startsWith('../') ||
    path.posix.isAbsolute(normalized)
  ) {
    throw new Error(`Ugyldig bildesti: ${rawPath}`);
  }

  return normalized;
}

function keyFromAbsolutePath(absolutePath: string, imageFolder: string): string | null {
  const relative = path.relative(imageFolder, absolutePath);
  if (
    relative === '' ||
    path.isAbsolute(relative) ||
    relative === '..' ||
    relative.startsWith(`..${path.sep}`)
  ) {
    return null;
  }
  return normalizeMediaKey(relative);
}

async function loadStore(): Promise<VerifiedStore> {
  try {
    const raw = await fs.promises.readFile(STORE_FILE, 'utf8');
    const parsed = JSON.parse(raw) as Partial<VerifiedStore>;

    if (parsed.version !== STORE_VERSION || !parsed.photos || typeof parsed.photos !== 'object') {
      throw new Error('ukjent eller ugyldig format');
    }

    const photos: Record<string, VerifiedEntry> = {};
    for (const [rawKey, value] of Object.entries(parsed.photos)) {
      const key = normalizeMediaKey(rawKey);
      if (!value || typeof value.verifiedAt !== 'string') {
        throw new Error(`ugyldig oppføring for ${key}`);
      }
      photos[key] = {
        verifiedAt: value.verifiedAt,
        ...(typeof value.verifiedBy === 'string' ? {verifiedBy: value.verifiedBy} : {})
      };
    }

    return {
      version: STORE_VERSION,
      albumName: ALBUM_NAME,
      keyword: ALBUM_KEYWORD,
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : new Date(0).toISOString(),
      photos
    };
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === 'ENOENT') {
      return emptyStore();
    }
    throw new Error(`Kan ikke lese ${STORE_FILE}: ${err.message}`);
  }
}

function serializeStore(snapshot: VerifiedStore): string {
  const photos = Object.fromEntries(
    Object.entries(snapshot.photos).sort(([a], [b]) => a.localeCompare(b))
  );
  return JSON.stringify({...snapshot, photos}, null, 2) + '\n';
}

function queueStoreWrite(): Promise<void> {
  store.updatedAt = new Date().toISOString();
  const snapshot = serializeStore(store);
  const tempFile = `${STORE_FILE}.tmp-${process.pid}`;

  const writeSnapshot = async (): Promise<void> => {
    await fs.promises.writeFile(tempFile, snapshot, {encoding: 'utf8', mode: 0o600});
    await fs.promises.rename(tempFile, STORE_FILE);
  };

  pendingWrite = pendingWrite.then(writeSnapshot, writeSnapshot);
  return pendingWrite;
}

function addKeyword(metadata: PhotoMetadata): void {
  metadata.keywords = metadata.keywords || [];
  if (!metadata.keywords.includes(ALBUM_KEYWORD)) {
    metadata.keywords.push(ALBUM_KEYWORD);
  }
}

function removeKeyword(metadata: PhotoMetadata): void {
  metadata.keywords = (metadata.keywords || []).filter(keyword => keyword !== ALBUM_KEYWORD);
}

async function ensureAlbum(extension: IExtensionObject<void>): Promise<void> {
  await extension._app.objectManagers.AlbumManager.addIfNotExistSavedSearch(ALBUM_NAME, {
    type: SearchQueryTypes.keyword,
    value: ALBUM_KEYWORD,
    matchType: TextSearchQueryMatchTypes.exact_match
  } as TextSearch, false);
}

function verifiedEntryFor(user: UserDTO): VerifiedEntry {
  return {
    verifiedAt: new Date().toISOString(),
    ...(user?.name ? {verifiedBy: user.name} : {})
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

export const init = async (extension: IExtensionObject<void>): Promise<void> => {
  store = await loadStore();
  await queueStoreWrite();
  await ensureAlbum(extension);

  extension.Logger.info(
    `Bekreftede observasjoner startet med ${Object.keys(store.photos).length} markerte bilder. Register: ${STORE_FILE}`
  );

  extension.events.gallery.MetadataLoader.loadPhotoMetadata.after(
    async (data: {input: [string]; output: PhotoMetadata}): Promise<PhotoMetadata> => {
      const key = keyFromAbsolutePath(data.input[0], extension.paths.ImageFolder);
      if (key && store.photos[key]) {
        addKeyword(data.output);
      }
      return data.output;
    }
  );

  extension.ui.addMediaButton({
    name: 'Bekreftet observasjon',
    svgIcon: verifiedIcon,
    minUserRole: UserRoles.User,
    apiPath: 'verify',
    reloadContent: true,
    skipVideos: true,
    alwaysVisible: true
  }, async (
    _params: ParamsDictionary,
    body: IMediaRequestBody,
    user: UserDTO,
    media: MediaEntity,
    repository: Repository<MediaEntity>
  ): Promise<void> => {
    const key = normalizeMediaKey(body.media);
    store.photos[key] = store.photos[key] || verifiedEntryFor(user);
    await queueStoreWrite();

    addKeyword(media.metadata as PhotoMetadata);
    await repository.save(media);
    await ensureAlbum(extension);
    extension.Logger.info(`Bekreftet observasjon: ${key}`);
  });

  extension.ui.addMediaButton({
    name: 'Fjern bekreftelse',
    svgIcon: removeIcon,
    minUserRole: UserRoles.User,
    apiPath: 'unverify',
    reloadContent: true,
    skipVideos: true,
    popup: {
      header: 'Fjern bekreftet observasjon',
      body: 'Vil du fjerne dette bildet fra albumet «Bekreftede observasjoner»?',
      buttonString: 'Fjern'
    }
  }, async (
    _params: ParamsDictionary,
    body: IMediaRequestBody,
    _user: UserDTO,
    media: MediaEntity,
    repository: Repository<MediaEntity>
  ): Promise<void> => {
    const key = normalizeMediaKey(body.media);
    delete store.photos[key];
    await queueStoreWrite();

    removeKeyword(media.metadata as PhotoMetadata);
    await repository.save(media);
    extension.Logger.info(`Fjernet bekreftet observasjon: ${key}`);
  });
};

export const cleanUp = async (): Promise<void> => {
  await pendingWrite;
};

export const _test = {
  normalizeMediaKey,
  keyFromAbsolutePath,
  addKeyword,
  removeKeyword,
  serializeStore
};
