<script setup>
import { ref, onMounted } from 'vue';
import { core } from '../api/client';

const healthLoading = ref(true);
const healthOk = ref(false);
onMounted(() => {
  core.health().then(r => { healthOk.value = r.data?.status === 'healthy'; }).catch(() => { healthOk.value = false; }).finally(() => { healthLoading.value = false; });
});
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-white">ViMax API Explorer</h1>
      <p class="mt-1 text-vimax-muted">Explore and call all ViMax API endpoints from the browser.</p>
    </div>

    <div class="card">
      <h2 class="mb-2 text-lg font-medium text-white">Quick links</h2>
      <ul class="grid gap-2 sm:grid-cols-2">
        <li><router-link to="/brands-games" class="text-vimax-accent hover:underline">Brands & Games</router-link> — List, create, get, generate brands and games</li>
        <li><router-link to="/characters" class="text-vimax-accent hover:underline">Characters</router-link> — List, get, add, generate characters (brand/game)</li>
        <li><router-link to="/pipelines" class="text-vimax-accent hover:underline">Pipelines</router-link> — 14 content pipelines (movie, video, lyrics, ad, etc.)</li>
        <li><router-link to="/tasks" class="text-vimax-accent hover:underline">Tasks</router-link> — Core and pipeline task status</li>
        <li><router-link to="/utils" class="text-vimax-accent hover:underline">Utilities</router-link> — Validate, fix, S3 docs</li>
      </ul>
    </div>

    <div class="card">
      <h2 class="mb-2 text-lg font-medium text-white">API health</h2>
      <div v-if="healthLoading" class="text-vimax-muted">Checking…</div>
      <div v-else-if="healthOk" class="flex items-center gap-2 text-vimax-emerald">✓ Connected</div>
      <div v-else class="text-vimax-rose">✗ Not reachable. Set API URL in the header (e.g. http://localhost:8000).</div>
    </div>
  </div>
</template>
