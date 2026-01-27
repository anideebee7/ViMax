<script setup>
import { ref, reactive } from 'vue';
import { core, pipelines } from '../api/client';

const loading = ref(false);
const res = ref(null);
const err = ref(null);

const coreTaskId = ref('');
const pipeTaskId = ref('');
const listFilters = reactive({ pipeline: '', status: '', limit: 50 });

function run(fn, ...args) {
  loading.value = true; err.value = null; res.value = null;
  fn(...args).then(r => { res.value = r.data; }).catch(e => { err.value = e.response?.data?.detail || e.message || String(e); }).finally(() => { loading.value = false; });
}

function getCoreTask() { if (!coreTaskId.value) return; run(core.getTask, coreTaskId.value); }
function getPipeTask() { if (!pipeTaskId.value) return; run(pipelines.getTask, pipeTaskId.value); }
function listPipeTasks() {
  const p = {};
  if (listFilters.pipeline) p.pipeline = listFilters.pipeline;
  if (listFilters.status) p.status = listFilters.status;
  if (listFilters.limit) p.limit = Number(listFilters.limit) || 50;
  run(pipelines.listTasks, p);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold text-white">Tasks</h1>
    <p class="text-vimax-muted">Check status of brand/game/character generation tasks and pipeline tasks.</p>

    <div class="grid gap-4 sm:grid-cols-2">
      <div class="card">
        <h3 class="mb-2 font-medium text-white">GET /tasks/:task_id</h3>
        <p class="mb-2 text-xs text-vimax-muted">Core generation (brands, games, characters)</p>
        <input v-model="coreTaskId" class="input-field mb-2" placeholder="task_id" />
        <button class="btn-primary" :disabled="loading" @click="getCoreTask">Get status</button>
      </div>
      <div class="card">
        <h3 class="mb-2 font-medium text-white">GET /pipelines/tasks/:task_id</h3>
        <p class="mb-2 text-xs text-vimax-muted">Pipeline tasks (movie, video, lyrics, etc.)</p>
        <input v-model="pipeTaskId" class="input-field mb-2" placeholder="task_id" />
        <button class="btn-primary" :disabled="loading" @click="getPipeTask">Get status</button>
      </div>
    </div>

    <div class="card">
      <h3 class="mb-2 font-medium text-white">GET /pipelines/tasks</h3>
      <p class="mb-3 text-xs text-vimax-muted">List pipeline tasks with optional filters</p>
      <div class="flex flex-wrap gap-2">
        <input v-model="listFilters.pipeline" class="input-field w-40" placeholder="pipeline (e.g. idea2movie)" />
        <select v-model="listFilters.status" class="input-field w-36">
          <option value="">status (any)</option>
          <option value="pending">pending</option>
          <option value="processing">processing</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
        <input v-model.number="listFilters.limit" class="input-field w-24" type="number" placeholder="50" />
        <button class="btn-primary" :disabled="loading" @click="listPipeTasks">List tasks</button>
      </div>
    </div>

    <div v-if="err" class="card border-vimax-rose/50 bg-vimax-rose/5"><pre class="overflow-auto text-sm text-vimax-rose">{{ err }}</pre></div>
    <div v-if="res" class="card"><pre class="max-h-96 overflow-auto text-xs text-slate-300">{{ JSON.stringify(res, null, 2) }}</pre></div>
    <div v-if="loading" class="text-vimax-muted">Loading…</div>
  </div>
</template>
