<script setup>
import { ref, onMounted } from 'vue';
import { RouterLink, RouterView } from 'vue-router';
import { getApiBase, setApiBase } from './api/client';
import './style.css';

const apiBase = ref('');
onMounted(() => { apiBase.value = getApiBase(); });
function onApiBaseBlur() {
  apiBase.value = setApiBase(apiBase.value) || getApiBase();
}
</script>

<template>
  <div class="min-h-screen bg-vimax-bg text-slate-200">
    <header class="sticky top-0 z-10 border-b border-vimax-border bg-vimax-bg/95 backdrop-blur">
      <div class="mx-auto flex h-14 max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2">
        <RouterLink to="/" class="flex items-center gap-2 font-semibold text-white">
          <span class="text-vimax-accent">ViMax</span>
          <span class="text-vimax-muted">API Explorer</span>
        </RouterLink>
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-xs text-vimax-muted">
            API URL
            <input
              v-model="apiBase"
              type="text"
              class="w-48 rounded border border-vimax-border bg-vimax-surface px-2 py-1 text-xs text-white placeholder-vimax-muted focus:border-vimax-accent focus:outline-none"
              placeholder="http://localhost:8000"
              @blur="onApiBaseBlur"
            />
          </label>
        <nav class="flex flex-wrap items-center gap-1 text-sm">
          <RouterLink to="/" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Home</RouterLink>
          <RouterLink to="/brands-games" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Brands & Games</RouterLink>
          <RouterLink to="/characters" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Characters</RouterLink>
          <RouterLink to="/pipelines" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Pipelines</RouterLink>
          <RouterLink to="/tasks" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Tasks</RouterLink>
          <RouterLink to="/utils" class="rounded px-3 py-2 text-vimax-muted hover:bg-vimax-surface hover:text-white" active-class="!text-vimax-accent !bg-vimax-surface">Utilities</RouterLink>
        </nav>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>
