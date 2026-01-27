<script setup>
import { ref, reactive } from 'vue';
import { core } from '../api/client';

const loading = ref(false);
const res = ref(null);
const err = ref(null);

const validate = reactive({ brand_id: '', game_id: '' });
const alias = reactive({ brand_id: '', char_id: '', alias: '' });
const mappingBrandId = ref('');
const fixBrandId = ref('');
const s3 = reactive({ prefix: '', max_keys: 100, key: '', expires: 3600 });

function run(fn, ...args) {
  loading.value = true; err.value = null; res.value = null;
  fn(...args).then(r => { res.value = r.data; }).catch(e => { err.value = e.response?.data?.detail || e.message || String(e); }).finally(() => { loading.value = false; });
}

function validateBrand() { if (!validate.brand_id) return; run(core.validateBrand, validate.brand_id); }
function validateGame() { if (!validate.game_id) return; run(core.validateGame, validate.game_id); }
function addAlias() { if (!alias.brand_id || !alias.char_id || !alias.alias) return; run(core.addCharacterAlias, alias.brand_id, alias.char_id, alias.alias); }
function getMapping() { if (!mappingBrandId.value) return; run(core.getCharactersMapping, mappingBrandId.value); }
function fixUrls() { if (!fixBrandId.value) return; run(core.fixBrandPublicUrls, fixBrandId.value); }
function getS3Docs() { run(core.getS3PatternDocs); }
function getS3Config() { run(core.getS3Config); }
function listS3() { run(() => core.listS3({ prefix: s3.prefix, max_keys: s3.max_keys })); }
function getS3Presign() { if (!s3.key) return; run(() => core.getS3PresignUrl({ key: s3.key, expires: s3.expires })); }
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold text-white">Utilities</h1>
    <p class="text-vimax-muted">Validate, fix, and inspect S3 structure.</p>

    <div class="grid gap-4 sm:grid-cols-2">
      <div class="card">
        <h3 class="mb-2 font-medium text-white">GET /validate/brand/:brand_id</h3>
        <input v-model="validate.brand_id" class="input-field mb-2" placeholder="brand_id" />
        <button class="btn-primary" :disabled="loading" @click="validateBrand">Validate brand</button>
      </div>
      <div class="card">
        <h3 class="mb-2 font-medium text-white">GET /validate/game/:game_id</h3>
        <input v-model="validate.game_id" class="input-field mb-2" placeholder="game_id" />
        <button class="btn-primary" :disabled="loading" @click="validateGame">Validate game</button>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">POST /brands/:brand_id/characters/:char_id/aliases</h3>
      <p class="mb-2 text-xs text-vimax-muted">Add alias (query: alias=...).</p>
      <div class="flex flex-wrap gap-2">
        <input v-model="alias.brand_id" class="input-field w-36" placeholder="brand_id" />
        <input v-model="alias.char_id" class="input-field w-36" placeholder="char_id" />
        <input v-model="alias.alias" class="input-field w-36" placeholder="alias" />
        <button class="btn-primary" :disabled="loading" @click="addAlias">Add alias</button>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">GET /brands/:brand_id/characters-mapping</h3>
      <div class="flex flex-wrap gap-2">
        <input v-model="mappingBrandId" class="input-field w-48" placeholder="brand_id" />
        <button class="btn-primary" :disabled="loading" @click="getMapping">Get mapping</button>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">POST /fix/brand/:brand_id/public-urls</h3>
      <p class="mb-2 text-xs text-vimax-muted">Fix public_urls to have both 'front' and 'portrait_front'.</p>
      <div class="flex flex-wrap gap-2">
        <input v-model="fixBrandId" class="input-field w-48" placeholder="brand_id" />
        <button class="btn-primary" :disabled="loading" @click="fixUrls">Fix</button>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">GET /docs/s3-pattern</h3>
      <button class="btn-primary" :disabled="loading" @click="getS3Docs">Get S3 pattern docs</button>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">S3 API</h3>
      <div class="space-y-3">
        <div>
          <span class="text-xs text-vimax-muted">GET /s3/config</span>
          <button class="btn-primary ml-2" :disabled="loading" @click="getS3Config">Get config</button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs text-vimax-muted">GET /s3/list</span>
          <input v-model="s3.prefix" class="input-field w-48" placeholder="prefix (e.g. brands)" />
          <input v-model.number="s3.max_keys" class="input-field w-20" type="number" placeholder="100" />
          <button class="btn-primary" :disabled="loading" @click="listS3">List</button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs text-vimax-muted">GET /s3/presign-url</span>
          <input v-model="s3.key" class="input-field w-64" placeholder="key (e.g. agent-assets/brands/x/Logo.png)" />
          <input v-model.number="s3.expires" class="input-field w-20" type="number" placeholder="3600" />
          <button class="btn-primary" :disabled="loading" @click="getS3Presign">Presign</button>
        </div>
      </div>
    </div>

    <div v-if="err" class="card border-vimax-rose/50 bg-vimax-rose/5"><pre class="overflow-auto text-sm text-vimax-rose">{{ err }}</pre></div>
    <div v-if="res" class="card"><pre class="max-h-96 overflow-auto text-xs text-slate-300">{{ JSON.stringify(res, null, 2) }}</pre></div>
    <div v-if="loading" class="text-vimax-muted">Loading…</div>
  </div>
</template>
