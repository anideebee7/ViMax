/**
 * ViMax API client
 * Base URL: VITE_API_URL or localStorage 'vimax_api_base' or http://localhost:8000
 */
import axios from 'axios';

function getBaseURL() {
  const fromEnv = import.meta.env.VITE_API_URL;
  const fromLs = typeof localStorage !== 'undefined' ? localStorage.getItem('vimax_api_base') : null;
  const u = (fromEnv || fromLs || 'http://localhost:8000').replace(/\/$/, '');
  return u || 'http://localhost:8000';
}

export function getApiBase() { return getBaseURL(); }

export function setApiBase(v) {
  const u = (String(v || '').trim() || 'http://localhost:8000').replace(/\/$/, '');
  if (typeof localStorage !== 'undefined') localStorage.setItem('vimax_api_base', u);
  client.defaults.baseURL = u;
  return u;
}

const client = axios.create({
  baseURL: getBaseURL(),
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000,
});

export default client;

// --- Core API (main.py) ---
export const core = {
  health: (ax = client) => ax.get('/health'),
  // Brands
  listBrands: (ax = client) => ax.get('/brands'),
  getBrand: (id, ax = client) => ax.get(`/brands/${id}`),
  createBrand: (body, ax = client) => ax.post('/brands', body),
  generateBrand: (body, ax = client) => ax.post('/brands/generate', body),
  // Games
  listGames: (ax = client) => ax.get('/games'),
  getGame: (id, ax = client) => ax.get(`/games/${id}`),
  createGame: (body, ax = client) => ax.post('/games', body),
  generateGame: (body, ax = client) => ax.post('/games/generate', body),
  // Characters (brand)
  listBrandCharacters: (brandId, ax = client) => ax.get(`/brands/${brandId}/characters`),
  getBrandCharacter: (brandId, charId, ax = client) => ax.get(`/brands/${brandId}/characters/${charId}`),
  addBrandCharacter: (brandId, body, qs, ax = client) => ax.post(`/brands/${brandId}/characters`, body, { params: qs }),
  generateBrandCharacter: (brandId, body, ax = client) => ax.post(`/brands/${brandId}/characters/generate`, body),
  // Characters (game)
  listGameCharacters: (gameId, ax = client) => ax.get(`/games/${gameId}/characters`),
  getGameCharacter: (gameId, charId, ax = client) => ax.get(`/games/${gameId}/characters/${charId}`),
  addGameCharacter: (gameId, body, qs, ax = client) => ax.post(`/games/${gameId}/characters`, body, { params: qs }),
  generateGameCharacter: (gameId, body, ax = client) => ax.post(`/games/${gameId}/characters/generate`, body),
  // Share
  shareBrandToGame: (gameId, brandId, ax = client) => ax.post(`/games/${gameId}/characters/share-from-brand/${brandId}`),
  // Tasks (core)
  getTask: (taskId, ax = client) => ax.get(`/tasks/${taskId}`),
  // Validate / Fix / Docs
  validateBrand: (brandId, ax = client) => ax.get(`/validate/brand/${brandId}`),
  validateGame: (gameId, ax = client) => ax.get(`/validate/game/${gameId}`),
  addCharacterAlias: (brandId, charId, alias, ax = client) => ax.post(`/brands/${brandId}/characters/${charId}/aliases`, null, { params: { alias } }),
  getCharactersMapping: (brandId, ax = client) => ax.get(`/brands/${brandId}/characters-mapping`),
  fixBrandPublicUrls: (brandId, ax = client) => ax.post(`/fix/brand/${brandId}/public-urls`),
  getS3PatternDocs: (ax = client) => ax.get('/docs/s3-pattern'),
  // S3 API
  getS3Config: (ax = client) => ax.get('/s3/config'),
  getS3PresignUrl: (params, ax = client) => ax.get('/s3/presign-url', { params }),
  listS3: (params, ax = client) => ax.get('/s3/list', { params }),
};

// --- Pipeline API (pipeline_routes.py) ---
export const pipelines = {
  getTask: (taskId, ax = client) => ax.get(`/pipelines/tasks/${taskId}`),
  listTasks: (params, ax = client) => ax.get('/pipelines/tasks', { params }),
  getOverview: (ax = client) => ax.get('/pipelines/docs/overview'),
  // 14 pipeline endpoints
  movie: (body, configPath, ax = client) => ax.post('/pipelines/movie', body, { params: configPath ? { config_path: configPath } : {} }),
  shortmovie: (body, configPath, ax = client) => ax.post('/pipelines/shortmovie', body, { params: configPath ? { config_path: configPath } : {} }),
  shortmovieVideo: (body, configPath, ax = client) => ax.post('/pipelines/shortmovie-video', body, { params: configPath ? { config_path: configPath } : {} }),
  lyrics: (body, configPath, ax = client) => ax.post('/pipelines/lyrics', body, { params: configPath ? { config_path: configPath } : {} }),
  documentary: (body, configPath, ax = client) => ax.post('/pipelines/documentary', body, { params: configPath ? { config_path: configPath } : {} }),
  ad: (body, configPath, ax = client) => ax.post('/pipelines/ad', body, { params: configPath ? { config_path: configPath } : {} }),
  video: (body, configPath, ax = client) => ax.post('/pipelines/video', body, { params: configPath ? { config_path: configPath } : {} }),
  script2video: (body, configPath, ax = client) => ax.post('/pipelines/script2video', body, { params: configPath ? { config_path: configPath } : {} }),
  song: (body, configPath, ax = client) => ax.post('/pipelines/song', body, { params: configPath ? { config_path: configPath } : {} }),
  musicvideo: (body, configPath, ax = client) => ax.post('/pipelines/musicvideo', body, { params: configPath ? { config_path: configPath } : {} }),
  kidsmovie: (body, configPath, ax = client) => ax.post('/pipelines/kidsmovie', body, { params: configPath ? { config_path: configPath } : {} }),
  learningseries: (body, configPath, ax = client) => ax.post('/pipelines/learningseries', body, { params: configPath ? { config_path: configPath } : {} }),
  adbanners: (body, configPath, ax = client) => ax.post('/pipelines/adbanners', body, { params: configPath ? { config_path: configPath } : {} }),
  podcast2video: (body, configPath, ax = client) => ax.post('/pipelines/podcast2video', body, { params: configPath ? { config_path: configPath } : {} }),
};
