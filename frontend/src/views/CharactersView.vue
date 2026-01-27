<script setup>
import { ref, reactive } from 'vue';
import { core } from '../api/client';

const parentType = ref('brand');
const loading = ref(false);
const res = ref(null);
const err = ref(null);

const ids = reactive({ parent: '', char: '' });
const add = reactive({ name: '', identifier_in_scene: '', static_features: '', dynamic_features: 'None', backstory: '', personality: '', role: '', generate_images: true, generate_voice: true });
const gen = reactive({ prompt: '', style: '3D animated cartoon', generate_images: true, generate_voice: true });

function run(fn, ...args) {
  loading.value = true; err.value = null; res.value = null;
  fn(...args).then(r => { res.value = r.data; }).catch(e => { err.value = e.response?.data?.detail || e.message || String(e); }).finally(() => { loading.value = false; });
}

function listChars() {
  if (!ids.parent) return;
  if (parentType.value === 'brand') run(core.listBrandCharacters, ids.parent);
  else run(core.listGameCharacters, ids.parent);
}
function getChar() {
  if (!ids.parent || !ids.char) return;
  if (parentType.value === 'brand') run(core.getBrandCharacter, ids.parent, ids.char);
  else run(core.getGameCharacter, ids.parent, ids.char);
}
function addChar() {
  if (!ids.parent) return;
  const body = { name: add.name, identifier_in_scene: add.identifier_in_scene, static_features: add.static_features, dynamic_features: add.dynamic_features || 'None', backstory: add.backstory || undefined, personality: add.personality || undefined, role: add.role || undefined };
  const qs = { generate_images: add.generate_images, generate_voice: add.generate_voice };
  if (parentType.value === 'brand') run(core.addBrandCharacter, ids.parent, body, qs);
  else run(core.addGameCharacter, ids.parent, body, qs);
}
function generateChar() {
  if (!ids.parent) return;
  const body = { prompt: gen.prompt, style: gen.style, generate_images: gen.generate_images, generate_voice: gen.generate_voice };
  if (parentType.value === 'brand') run(core.generateBrandCharacter, ids.parent, body);
  else run(core.generateGameCharacter, ids.parent, body);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold text-white">Characters</h1>

    <div class="card">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-2">
          <span class="text-vimax-muted">Parent</span>
          <select v-model="parentType" class="input-field w-28">
            <option value="brand">Brand</option>
            <option value="game">Game</option>
          </select>
        </label>
        <input v-model="ids.parent" class="input-field w-48" :placeholder="parentType === 'brand' ? 'brand_id' : 'game_id'" />
      </div>

      <div class="grid gap-3 sm:grid-cols-2">
        <div class="card">
          <h3 class="mb-2 font-medium text-white">GET /{{ parentType }}s/:id/characters</h3>
          <button class="btn-primary" :disabled="loading" @click="listChars">List characters</button>
        </div>
        <div class="card">
          <h3 class="mb-2 font-medium text-white">GET /{{ parentType }}s/:id/characters/:char_id</h3>
          <input v-model="ids.char" class="input-field mb-2" placeholder="char_id" />
          <button class="btn-primary" :disabled="loading" @click="getChar">Get character</button>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-3 font-medium text-white">POST /{{ parentType }}s/:id/characters</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">name *</label><input v-model="add.name" class="input-field" /></div>
        <div><label class="label">identifier_in_scene *</label><input v-model="add.identifier_in_scene" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">static_features *</label><textarea v-model="add.static_features" class="input-field" rows="2" /></div>
        <div><label class="label">dynamic_features</label><input v-model="add.dynamic_features" class="input-field" /></div>
        <div><label class="label">backstory</label><input v-model="add.backstory" class="input-field" /></div>
        <div><label class="label">personality</label><input v-model="add.personality" class="input-field" /></div>
        <div><label class="label">role</label><input v-model="add.role" class="input-field" /></div>
        <div class="flex gap-4">
          <label class="flex items-center gap-2"><input v-model="add.generate_images" type="checkbox" /> generate_images</label>
          <label class="flex items-center gap-2"><input v-model="add.generate_voice" type="checkbox" /> generate_voice</label>
        </div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="addChar">Add character</button>
    </div>

    <div class="card">
      <h3 class="mb-3 font-medium text-white">POST /{{ parentType }}s/:id/characters/generate</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">prompt *</label><input v-model="gen.prompt" class="input-field" placeholder="Describe the character" /></div>
        <div><label class="label">style</label><input v-model="gen.style" class="input-field" /></div>
        <div class="flex gap-4">
          <label class="flex items-center gap-2"><input v-model="gen.generate_images" type="checkbox" /> generate_images</label>
          <label class="flex items-center gap-2"><input v-model="gen.generate_voice" type="checkbox" /> generate_voice</label>
        </div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="generateChar">Generate character</button>
    </div>

    <div v-if="err" class="card border-vimax-rose/50 bg-vimax-rose/5"><pre class="overflow-auto text-sm text-vimax-rose">{{ err }}</pre></div>
    <div v-if="res" class="card space-y-3">
      <!-- S3 media: character portraits and voice -->
      <div v-if="res && res.public_urls && Object.keys(res.public_urls).length" class="flex flex-wrap items-start gap-4 border-b border-vimax-border pb-3">
        <template v-if="res.public_urls.front || res.public_urls.portrait_front">
          <div>
            <span class="label">Front</span>
            <img :src="res.public_urls.front || res.public_urls.portrait_front" alt="Front" class="mt-1 max-h-32 rounded border border-vimax-border object-contain" @error="($event.target).style.display='none'" />
          </div>
        </template>
        <template v-if="res.public_urls.side || res.public_urls.portrait_side">
          <div>
            <span class="label">Side</span>
            <img :src="res.public_urls.side || res.public_urls.portrait_side" alt="Side" class="mt-1 max-h-32 rounded border border-vimax-border object-contain" @error="($event.target).style.display='none'" />
          </div>
        </template>
        <template v-if="res.public_urls.back || res.public_urls.portrait_back">
          <div>
            <span class="label">Back</span>
            <img :src="res.public_urls.back || res.public_urls.portrait_back" alt="Back" class="mt-1 max-h-32 rounded border border-vimax-border object-contain" @error="($event.target).style.display='none'" />
          </div>
        </template>
        <template v-if="res.public_urls.voice">
          <div>
            <span class="label">Voice</span>
            <audio :src="res.public_urls.voice" controls class="mt-1 max-w-xs" />
          </div>
        </template>
      </div>
      <pre class="max-h-96 overflow-auto text-xs text-slate-300">{{ JSON.stringify(res, null, 2) }}</pre>
    </div>
    <div v-if="loading" class="text-vimax-muted">Loading…</div>
  </div>
</template>
