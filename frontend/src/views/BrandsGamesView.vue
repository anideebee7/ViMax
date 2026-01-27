<script setup>
import { ref, reactive } from 'vue';
import { core } from '../api/client';

const tab = ref('brands');
const loading = ref(false);
const res = ref(null);
const err = ref(null);

const brands = reactive({ list: [], id: '', create: { name: '', description: '', tagline: '', story: '', values: '', target_audience: '', visual_style: '' }, generate: { prompt: '', industry: '', style: '', generate_logo: true, num_characters: 3 } });
const games = reactive({ list: [], id: '', create: { name: '', description: '', genre: '', brand_id: '', platforms: 'mobile', story: '', mechanics: '', target_audience: '' }, generate: { prompt: '', genre: '', brand_id: '', platforms: 'mobile', generate_icon: true, num_characters: 4 } });
const share = reactive({ game_id: '', brand_id: '' });

function run(fn, ...args) {
  loading.value = true; err.value = null; res.value = null;
  fn(...args).then(r => { res.value = r.data; }).catch(e => { err.value = e.response?.data?.detail || e.message || String(e); }).finally(() => { loading.value = false; });
}

function listBrands() { run(core.listBrands); }
function getBrand() { if (!brands.id) return; run(core.getBrand, brands.id); }
function createBrand() {
  const b = { ...brands.create, values: brands.create.values ? brands.create.values.split(',').map(s => s.trim()).filter(Boolean) : undefined };
  run(core.createBrand, b);
}
function generateBrand() { run(core.generateBrand, brands.generate); }

function listGames() { run(core.listGames); }
function getGame() { if (!games.id) return; run(core.getGame, games.id); }
function createGame() {
  const g = { ...games.create, platforms: games.create.platforms ? games.create.platforms.split(',').map(s => s.trim()).filter(Boolean) : ['mobile'] };
  run(core.createGame, g);
}
function generateGame() {
  const g = { ...games.generate, platforms: (games.generate.platforms || 'mobile').split(',').map(s => s.trim()).filter(Boolean) };
  run(core.generateGame, g);
}

function shareToGame() { if (!share.game_id || !share.brand_id) return; run(core.shareBrandToGame, share.game_id, share.brand_id); }
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold text-white">Brands & Games</h1>

    <div class="flex gap-2 border-b border-vimax-border">
      <button :class="['px-4 py-2 text-sm font-medium', tab === 'brands' ? 'border-b-2 border-vimax-accent text-white' : 'text-vimax-muted hover:text-white']" @click="tab = 'brands'">Brands</button>
      <button :class="['px-4 py-2 text-sm font-medium', tab === 'games' ? 'border-b-2 border-vimax-accent text-white' : 'text-vimax-muted hover:text-white']" @click="tab = 'games'">Games</button>
    </div>

    <!-- Brands -->
    <div v-show="tab === 'brands'" class="space-y-4">
      <div class="card">
        <h3 class="mb-3 font-medium text-white">GET /brands</h3>
        <button class="btn-primary" :disabled="loading" @click="listBrands">List brands</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">GET /brands/:id</h3>
        <input v-model="brands.id" class="input-field mb-2" placeholder="brand_id" />
        <button class="btn-primary" :disabled="loading" @click="getBrand">Get brand</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">POST /brands</h3>
        <div class="grid gap-2 sm:grid-cols-2">
          <div><label class="label">name *</label><input v-model="brands.create.name" class="input-field" /></div>
          <div><label class="label">description *</label><input v-model="brands.create.description" class="input-field" /></div>
          <div><label class="label">tagline</label><input v-model="brands.create.tagline" class="input-field" /></div>
          <div><label class="label">story</label><input v-model="brands.create.story" class="input-field" /></div>
          <div><label class="label">values (comma)</label><input v-model="brands.create.values" class="input-field" /></div>
          <div><label class="label">target_audience</label><input v-model="brands.create.target_audience" class="input-field" /></div>
          <div><label class="label">visual_style</label><input v-model="brands.create.visual_style" class="input-field" /></div>
        </div>
        <button class="btn-primary mt-2" :disabled="loading" @click="createBrand">Create brand</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">POST /brands/generate</h3>
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="sm:col-span-2"><label class="label">prompt *</label><input v-model="brands.generate.prompt" class="input-field" placeholder="Describe the brand" /></div>
          <div><label class="label">industry</label><input v-model="brands.generate.industry" class="input-field" /></div>
          <div><label class="label">style</label><input v-model="brands.generate.style" class="input-field" /></div>
          <div><label class="label">generate_logo</label><input v-model="brands.generate.generate_logo" type="checkbox" class="mt-1" /></div>
          <div><label class="label">num_characters</label><input v-model.number="brands.generate.num_characters" class="input-field" type="number" /></div>
        </div>
        <button class="btn-primary mt-2" :disabled="loading" @click="generateBrand">Generate brand</button>
      </div>
    </div>

    <!-- Games -->
    <div v-show="tab === 'games'" class="space-y-4">
      <div class="card">
        <h3 class="mb-3 font-medium text-white">GET /games</h3>
        <button class="btn-primary" :disabled="loading" @click="listGames">List games</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">GET /games/:id</h3>
        <input v-model="games.id" class="input-field mb-2" placeholder="game_id" />
        <button class="btn-primary" :disabled="loading" @click="getGame">Get game</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">POST /games</h3>
        <div class="grid gap-2 sm:grid-cols-2">
          <div><label class="label">name *</label><input v-model="games.create.name" class="input-field" /></div>
          <div><label class="label">description *</label><input v-model="games.create.description" class="input-field" /></div>
          <div><label class="label">genre</label><input v-model="games.create.genre" class="input-field" /></div>
          <div><label class="label">brand_id</label><input v-model="games.create.brand_id" class="input-field" /></div>
          <div><label class="label">platforms (comma)</label><input v-model="games.create.platforms" class="input-field" placeholder="mobile, web" /></div>
          <div><label class="label">story</label><input v-model="games.create.story" class="input-field" /></div>
          <div><label class="label">mechanics</label><input v-model="games.create.mechanics" class="input-field" /></div>
          <div><label class="label">target_audience</label><input v-model="games.create.target_audience" class="input-field" /></div>
        </div>
        <button class="btn-primary mt-2" :disabled="loading" @click="createGame">Create game</button>
      </div>
      <div class="card">
        <h3 class="mb-3 font-medium text-white">POST /games/generate</h3>
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="sm:col-span-2"><label class="label">prompt *</label><input v-model="games.generate.prompt" class="input-field" placeholder="Describe the game" /></div>
          <div><label class="label">genre</label><input v-model="games.generate.genre" class="input-field" /></div>
          <div><label class="label">brand_id</label><input v-model="games.generate.brand_id" class="input-field" /></div>
          <div><label class="label">platforms (comma)</label><input v-model="games.generate.platforms" class="input-field" placeholder="mobile, web" /></div>
          <div><label class="label">generate_icon</label><input v-model="games.generate.generate_icon" type="checkbox" class="mt-1" /></div>
          <div><label class="label">num_characters</label><input v-model.number="games.generate.num_characters" class="input-field" type="number" /></div>
        </div>
        <button class="btn-primary mt-2" :disabled="loading" @click="generateGame">Generate game</button>
      </div>

      <div class="card">
        <h3 class="mb-3 font-medium text-white">POST /games/:game_id/characters/share-from-brand/:brand_id</h3>
        <div class="flex flex-wrap gap-2">
          <input v-model="share.game_id" class="input-field w-40" placeholder="game_id" />
          <input v-model="share.brand_id" class="input-field w-40" placeholder="brand_id" />
          <button class="btn-primary" :disabled="loading" @click="shareToGame">Share characters</button>
        </div>
      </div>
    </div>

    <div v-if="err" class="card border-vimax-rose/50 bg-vimax-rose/5"><pre class="overflow-auto text-sm text-vimax-rose">{{ err }}</pre></div>
    <div v-if="res" class="card space-y-3">
      <!-- S3 media: brand logo or game icon -->
      <div v-if="res && !Array.isArray(res) && res.public_url" class="flex flex-wrap items-start gap-3 border-b border-vimax-border pb-3">
        <template v-if="res.media?.logo?.primary">
          <div>
            <span class="label">Logo</span>
            <img :src="(res.public_url || '').replace(/\/$/, '') + '/' + res.media.logo.primary" alt="Logo" class="mt-1 max-h-24 rounded border border-vimax-border object-contain" @error="($event.target).style.display='none'" />
          </div>
        </template>
        <template v-if="res.media?.icon?.primary">
          <div>
            <span class="label">Icon</span>
            <img :src="(res.public_url || '').replace(/\/$/, '') + '/' + res.media.icon.primary" alt="Icon" class="mt-1 max-h-24 rounded border border-vimax-border object-contain" @error="($event.target).style.display='none'" />
          </div>
        </template>
      </div>
      <pre class="max-h-96 overflow-auto text-xs text-slate-300">{{ JSON.stringify(res, null, 2) }}</pre>
    </div>
    <div v-if="loading" class="text-vimax-muted">Loading…</div>
  </div>
</template>
