<script setup>
import { ref, reactive } from 'vue';
import { pipelines } from '../api/client';

const selected = ref('movie');
const loading = ref(false);
const res = ref(null);
const err = ref(null);

const forms = reactive({
  movie: { premise: '', genre: 'drama', target_runtime_minutes: 90, audience: '', style: 'cinematic', trendy: false, content_format: 'live_action' },
  shortmovie: { premise: '', genre: 'drama', target_duration_minutes: 15, audience: '', style: 'cinematic', trendy: false, content_format: 'live_action' },
  shortmovieVideo: { premise: '', genre: 'drama', target_duration_minutes: 15, audience: '', style: 'cinematic', trendy: false, content_format: 'animated', generate_storyboard_images: true, generate_videos: true, max_scenes: null, brand_id: '', game_id: '', character_names: '' },
  lyrics: { idea: '', user_requirement: '', style: '', genre: '', mood: '', audience: '', trendy: false },
  documentary: { topic: '', target_duration_minutes: 30, research_depth: 'moderate', audience: '', style: 'informative and engaging', trendy: false, auto_ideate: false, ideation_mode: 'creativity', brand_hint: '', content_format: 'live_action' },
  ad: { brand: '', product: '', campaign_goal: '', audience: '', ad_format: '30s', generate_visuals: true, generate_videos: false, trendy: false, auto_ideate: false, ideation_mode: 'viral' },
  video: { idea: '', user_requirement: '', style: 'cinematic', audience: '', trendy: false, auto_ideate: false, ideation_mode: 'creativity', brand_hint: '', content_format: 'live_action', shorts_mode: false },
  script2video: { script: '', user_requirement: '', style: 'realistic', audience: '', trendy: false, content_format: '' },
  song: { idea: '', user_requirement: '', style: 'pop', audience: '', trendy: false, auto_ideate: false, ideation_mode: 'creativity', brand_hint: '' },
  musicvideo: { song_title: '', lyrics: '', genre: '', mood: '', song_structure: '', style: 'cinematic', audience: '', generate_storyboard_images: true, trendy: false, kids_mode: false },
  kidsmovie: { story_idea: '', age_group: '6-8', characters: '', moral_lesson: '', target_duration_minutes: 15, style: 'colorful 3D animation', audience: '', generate_character_art: true, trendy: false, auto_ideate: false, ideation_mode: 'creativity', brand_hint: '' },
  learningseries: { topic: '', num_episodes: 5, episode_duration_minutes: 10, audience: '', skill_level: 'beginner', learning_goals: '', trendy: false, generate_images: true, generate_videos: true, visual_style: 'professional educational, clean, modern', max_episodes_to_generate: null, brand_id: '', game_id: '', character_names: '', featured_character: '' },
  adbanners: { brand_or_game: '', entity_type: 'brand', brief: '', audience: 'General mobile and desktop users, 18-44', campaign_goal: 'Conversions and installs', platforms: 'Google Display, Meta (Facebook/Instagram), programmatic', trendy: false, brand_id: '', game_id: '', num_concepts: 5, sizes: '' },
  podcast2video: { script_text: '', script_path: '', max_scenes: null, audience: '', trendy: false, auto_ideate: false, ideation_mode: 'podcast', topic_area: '', brand_id: 'intelli-verse-x' },
});

function omitEmpty(o) {
  const r = {};
  for (const [k, v] of Object.entries(o)) {
    if (v === '' || v === null || v === undefined) continue;
    if (typeof v === 'string' && !v.trim()) continue;
    r[k] = v;
  }
  return r;
}

function run(fn, body, configPath = '') {
  loading.value = true; err.value = null; res.value = null;
  const b = omitEmpty(body);
  (configPath ? fn(b, configPath) : fn(b)).then(r => { res.value = r.data; }).catch(e => { err.value = e.response?.data?.detail || e.message || String(e); }).finally(() => { loading.value = false; });
}

function submitMovie() { run(pipelines.movie, { ...forms.movie, content_format: forms.movie.content_format }); }
function submitShortmovie() { run(pipelines.shortmovie, { ...forms.shortmovie, content_format: forms.shortmovie.content_format }); }
function submitShortmovieVideo() {
  const b = { ...forms.shortmovieVideo, content_format: forms.shortmovieVideo.content_format };
  if (b.character_names) b.character_names = b.character_names.split(',').map(s => s.trim()).filter(Boolean);
  if (b.max_scenes != null) b.max_scenes = Number(b.max_scenes);
  run(pipelines.shortmovieVideo, b);
}
function submitLyrics() { run(pipelines.lyrics, forms.lyrics); }
function submitDocumentary() { run(pipelines.documentary, { ...forms.documentary, ideation_mode: forms.documentary.ideation_mode, content_format: forms.documentary.content_format }); }
function submitAd() { run(pipelines.ad, { ...forms.ad, ideation_mode: forms.ad.ideation_mode }); }
function submitVideo() { run(pipelines.video, { ...forms.video, ideation_mode: forms.video.ideation_mode, content_format: forms.video.content_format }); }
function submitScript2video() { run(pipelines.script2video, { ...forms.script2video, content_format: forms.script2video.content_format || null }); }
function submitSong() { run(pipelines.song, { ...forms.song, ideation_mode: forms.song.ideation_mode }); }
function submitMusicvideo() { run(pipelines.musicvideo, forms.musicvideo); }
function submitKidsmovie() { run(pipelines.kidsmovie, { ...forms.kidsmovie, ideation_mode: forms.kidsmovie.ideation_mode }); }
function submitLearningseries() {
  const b = { ...forms.learningseries };
  if (b.character_names) b.character_names = b.character_names.split(',').map(s => s.trim()).filter(Boolean);
  if (b.max_episodes_to_generate != null) b.max_episodes_to_generate = Number(b.max_episodes_to_generate);
  run(pipelines.learningseries, b);
}
function submitAdbanners() {
  const b = { ...forms.adbanners };
  if (b.sizes) b.sizes = b.sizes.split(',').map(s => s.trim()).filter(Boolean);
  run(pipelines.adbanners, b);
}
function submitPodcast2video() { run(pipelines.podcast2video, { ...forms.podcast2video, ideation_mode: forms.podcast2video.ideation_mode }); }
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold text-white">Pipelines</h1>
    <p class="text-vimax-muted">All 14 content generation pipelines. Each returns a task_id; check status under Tasks.</p>

    <div class="card">
      <label class="label">Pipeline</label>
      <select v-model="selected" class="input-field max-w-xs">
        <option value="movie">movie</option>
        <option value="shortmovie">shortmovie</option>
        <option value="shortmovieVideo">shortmovie-video</option>
        <option value="lyrics">lyrics</option>
        <option value="documentary">documentary</option>
        <option value="ad">ad</option>
        <option value="video">video</option>
        <option value="script2video">script2video</option>
        <option value="song">song</option>
        <option value="musicvideo">musicvideo</option>
        <option value="kidsmovie">kidsmovie</option>
        <option value="learningseries">learningseries</option>
        <option value="adbanners">adbanners</option>
        <option value="podcast2video">podcast2video</option>
      </select>
    </div>

    <!-- movie -->
    <div v-show="selected === 'movie'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/movie</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">premise *</label><input v-model="forms.movie.premise" class="input-field" /></div>
        <div><label class="label">genre</label><input v-model="forms.movie.genre" class="input-field" /></div>
        <div><label class="label">target_runtime_minutes</label><input v-model.number="forms.movie.target_runtime_minutes" class="input-field" type="number" /></div>
        <div><label class="label">audience</label><input v-model="forms.movie.audience" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.movie.style" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.movie.content_format" class="input-field"><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.movie.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitMovie">Run</button>
    </div>

    <!-- shortmovie -->
    <div v-show="selected === 'shortmovie'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/shortmovie</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">premise *</label><input v-model="forms.shortmovie.premise" class="input-field" /></div>
        <div><label class="label">genre</label><input v-model="forms.shortmovie.genre" class="input-field" /></div>
        <div><label class="label">target_duration_minutes</label><input v-model.number="forms.shortmovie.target_duration_minutes" class="input-field" type="number" /></div>
        <div><label class="label">audience</label><input v-model="forms.shortmovie.audience" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.shortmovie.style" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.shortmovie.content_format" class="input-field"><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.shortmovie.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitShortmovie">Run</button>
    </div>

    <!-- shortmovie-video -->
    <div v-show="selected === 'shortmovieVideo'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/shortmovie-video</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">premise *</label><input v-model="forms.shortmovieVideo.premise" class="input-field" /></div>
        <div><label class="label">genre</label><input v-model="forms.shortmovieVideo.genre" class="input-field" /></div>
        <div><label class="label">target_duration_minutes</label><input v-model.number="forms.shortmovieVideo.target_duration_minutes" class="input-field" type="number" /></div>
        <div><label class="label">audience</label><input v-model="forms.shortmovieVideo.audience" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.shortmovieVideo.style" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.shortmovieVideo.content_format" class="input-field"><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.shortmovieVideo.generate_storyboard_images" type="checkbox" /> generate_storyboard_images</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.shortmovieVideo.generate_videos" type="checkbox" /> generate_videos</label></div>
        <div><label class="label">max_scenes</label><input v-model.number="forms.shortmovieVideo.max_scenes" class="input-field" type="number" placeholder="omit" /></div>
        <div><label class="label">brand_id</label><input v-model="forms.shortmovieVideo.brand_id" class="input-field" /></div>
        <div><label class="label">game_id</label><input v-model="forms.shortmovieVideo.game_id" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">character_names (comma)</label><input v-model="forms.shortmovieVideo.character_names" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.shortmovieVideo.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitShortmovieVideo">Run</button>
    </div>

    <!-- lyrics -->
    <div v-show="selected === 'lyrics'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/lyrics</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">idea *</label><input v-model="forms.lyrics.idea" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">user_requirement *</label><input v-model="forms.lyrics.user_requirement" class="input-field" /></div>
        <div><label class="label">style *</label><input v-model="forms.lyrics.style" class="input-field" /></div>
        <div><label class="label">genre</label><input v-model="forms.lyrics.genre" class="input-field" /></div>
        <div><label class="label">mood</label><input v-model="forms.lyrics.mood" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.lyrics.audience" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.lyrics.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitLyrics">Run</button>
    </div>

    <!-- documentary -->
    <div v-show="selected === 'documentary'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/documentary</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">topic</label><input v-model="forms.documentary.topic" class="input-field" /></div>
        <div><label class="label">target_duration_minutes</label><input v-model.number="forms.documentary.target_duration_minutes" class="input-field" type="number" /></div>
        <div><label class="label">research_depth</label><input v-model="forms.documentary.research_depth" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.documentary.audience" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.documentary.style" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.documentary.content_format" class="input-field"><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.documentary.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.documentary.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="label">brand_hint</label><input v-model="forms.documentary.brand_hint" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.documentary.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitDocumentary">Run</button>
    </div>

    <!-- ad -->
    <div v-show="selected === 'ad'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/ad</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">brand</label><input v-model="forms.ad.brand" class="input-field" /></div>
        <div><label class="label">product</label><input v-model="forms.ad.product" class="input-field" /></div>
        <div><label class="label">campaign_goal</label><input v-model="forms.ad.campaign_goal" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.ad.audience" class="input-field" /></div>
        <div><label class="label">ad_format</label><input v-model="forms.ad.ad_format" class="input-field" placeholder="30s" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.ad.generate_visuals" type="checkbox" /> generate_visuals</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.ad.generate_videos" type="checkbox" /> generate_videos</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.ad.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.ad.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.ad.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitAd">Run</button>
    </div>

    <!-- video -->
    <div v-show="selected === 'video'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/video</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">idea</label><input v-model="forms.video.idea" class="input-field" /></div>
        <div><label class="label">user_requirement</label><input v-model="forms.video.user_requirement" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.video.style" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.video.audience" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.video.content_format" class="input-field"><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.video.shorts_mode" type="checkbox" /> shorts_mode</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.video.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.video.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="label">brand_hint</label><input v-model="forms.video.brand_hint" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.video.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitVideo">Run</button>
    </div>

    <!-- script2video -->
    <div v-show="selected === 'script2video'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/script2video</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">script *</label><textarea v-model="forms.script2video.script" class="input-field" rows="4" /></div>
        <div class="sm:col-span-2"><label class="label">user_requirement *</label><input v-model="forms.script2video.user_requirement" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.script2video.style" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.script2video.audience" class="input-field" /></div>
        <div><label class="label">content_format</label><select v-model="forms.script2video.content_format" class="input-field"><option value="">—</option><option value="live_action">live_action</option><option value="animated">animated</option><option value="hybrid">hybrid</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.script2video.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitScript2video">Run</button>
    </div>

    <!-- song -->
    <div v-show="selected === 'song'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/song</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">idea</label><input v-model="forms.song.idea" class="input-field" /></div>
        <div><label class="label">user_requirement</label><input v-model="forms.song.user_requirement" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.song.style" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.song.audience" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.song.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.song.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="label">brand_hint</label><input v-model="forms.song.brand_hint" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.song.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitSong">Run</button>
    </div>

    <!-- musicvideo -->
    <div v-show="selected === 'musicvideo'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/musicvideo</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">song_title *</label><input v-model="forms.musicvideo.song_title" class="input-field" /></div>
        <div><label class="label">genre *</label><input v-model="forms.musicvideo.genre" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">lyrics *</label><textarea v-model="forms.musicvideo.lyrics" class="input-field" rows="4" /></div>
        <div><label class="label">mood *</label><input v-model="forms.musicvideo.mood" class="input-field" /></div>
        <div><label class="label">song_structure</label><input v-model="forms.musicvideo.song_structure" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.musicvideo.style" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.musicvideo.audience" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.musicvideo.generate_storyboard_images" type="checkbox" /> generate_storyboard_images</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.musicvideo.kids_mode" type="checkbox" /> kids_mode</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.musicvideo.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitMusicvideo">Run</button>
    </div>

    <!-- kidsmovie -->
    <div v-show="selected === 'kidsmovie'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/kidsmovie</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">story_idea</label><input v-model="forms.kidsmovie.story_idea" class="input-field" /></div>
        <div><label class="label">age_group</label><input v-model="forms.kidsmovie.age_group" class="input-field" placeholder="3-5, 6-8, 9-12" /></div>
        <div><label class="label">target_duration_minutes</label><input v-model.number="forms.kidsmovie.target_duration_minutes" class="input-field" type="number" /></div>
        <div><label class="label">characters</label><input v-model="forms.kidsmovie.characters" class="input-field" /></div>
        <div><label class="label">moral_lesson</label><input v-model="forms.kidsmovie.moral_lesson" class="input-field" /></div>
        <div><label class="label">style</label><input v-model="forms.kidsmovie.style" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.kidsmovie.audience" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.kidsmovie.generate_character_art" type="checkbox" /> generate_character_art</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.kidsmovie.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.kidsmovie.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="label">brand_hint</label><input v-model="forms.kidsmovie.brand_hint" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.kidsmovie.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitKidsmovie">Run</button>
    </div>

    <!-- learningseries -->
    <div v-show="selected === 'learningseries'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/learningseries</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">topic *</label><input v-model="forms.learningseries.topic" class="input-field" /></div>
        <div><label class="label">num_episodes</label><input v-model.number="forms.learningseries.num_episodes" class="input-field" type="number" /></div>
        <div><label class="label">episode_duration_minutes</label><input v-model.number="forms.learningseries.episode_duration_minutes" class="input-field" type="number" /></div>
        <div><label class="label">audience</label><input v-model="forms.learningseries.audience" class="input-field" /></div>
        <div><label class="label">skill_level</label><input v-model="forms.learningseries.skill_level" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">learning_goals</label><input v-model="forms.learningseries.learning_goals" class="input-field" /></div>
        <div><label class="label">visual_style</label><input v-model="forms.learningseries.visual_style" class="input-field" /></div>
        <div><label class="label">max_episodes_to_generate</label><input v-model.number="forms.learningseries.max_episodes_to_generate" class="input-field" type="number" placeholder="omit" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.learningseries.generate_images" type="checkbox" /> generate_images</label></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.learningseries.generate_videos" type="checkbox" /> generate_videos</label></div>
        <div><label class="label">brand_id</label><input v-model="forms.learningseries.brand_id" class="input-field" /></div>
        <div><label class="label">game_id</label><input v-model="forms.learningseries.game_id" class="input-field" /></div>
        <div><label class="label">character_names (comma)</label><input v-model="forms.learningseries.character_names" class="input-field" /></div>
        <div><label class="label">featured_character</label><input v-model="forms.learningseries.featured_character" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.learningseries.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitLearningseries">Run</button>
    </div>

    <!-- adbanners -->
    <div v-show="selected === 'adbanners'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/adbanners</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div><label class="label">brand_or_game *</label><input v-model="forms.adbanners.brand_or_game" class="input-field" /></div>
        <div><label class="label">entity_type</label><select v-model="forms.adbanners.entity_type" class="input-field"><option value="brand">brand</option><option value="game">game</option></select></div>
        <div class="sm:col-span-2"><label class="label">brief</label><input v-model="forms.adbanners.brief" class="input-field" /></div>
        <div><label class="label">audience</label><input v-model="forms.adbanners.audience" class="input-field" /></div>
        <div><label class="label">campaign_goal</label><input v-model="forms.adbanners.campaign_goal" class="input-field" /></div>
        <div class="sm:col-span-2"><label class="label">platforms</label><input v-model="forms.adbanners.platforms" class="input-field" /></div>
        <div><label class="label">brand_id</label><input v-model="forms.adbanners.brand_id" class="input-field" /></div>
        <div><label class="label">game_id</label><input v-model="forms.adbanners.game_id" class="input-field" /></div>
        <div><label class="label">num_concepts</label><input v-model.number="forms.adbanners.num_concepts" class="input-field" type="number" /></div>
        <div><label class="label">sizes (comma, omit=all)</label><input v-model="forms.adbanners.sizes" class="input-field" placeholder="medium_rectangle, leaderboard" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.adbanners.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitAdbanners">Run</button>
    </div>

    <!-- podcast2video -->
    <div v-show="selected === 'podcast2video'" class="card">
      <h3 class="mb-3 font-medium text-white">POST /pipelines/podcast2video</h3>
      <div class="grid gap-2 sm:grid-cols-2">
        <div class="sm:col-span-2"><label class="label">script_text</label><textarea v-model="forms.podcast2video.script_text" class="input-field" rows="4" placeholder="Or use script_path" /></div>
        <div><label class="label">script_path</label><input v-model="forms.podcast2video.script_path" class="input-field" placeholder="Path to PDF/TXT" /></div>
        <div><label class="label">max_scenes</label><input v-model.number="forms.podcast2video.max_scenes" class="input-field" type="number" placeholder="omit" /></div>
        <div><label class="label">audience</label><input v-model="forms.podcast2video.audience" class="input-field" /></div>
        <div><label class="label">topic_area</label><input v-model="forms.podcast2video.topic_area" class="input-field" /></div>
        <div><label class="label">brand_id</label><input v-model="forms.podcast2video.brand_id" class="input-field" /></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.podcast2video.auto_ideate" type="checkbox" /> auto_ideate</label></div>
        <div><label class="label">ideation_mode</label><select v-model="forms.podcast2video.ideation_mode" class="input-field"><option value="creativity">creativity</option><option value="trends">trends</option><option value="viral">viral</option><option value="brand">brand</option><option value="podcast">podcast</option></select></div>
        <div><label class="flex items-center gap-2"><input v-model="forms.podcast2video.trendy" type="checkbox" /> trendy</label></div>
      </div>
      <button class="btn-primary mt-2" :disabled="loading" @click="submitPodcast2video">Run</button>
    </div>

    <div v-if="err" class="card border-vimax-rose/50 bg-vimax-rose/5"><pre class="overflow-auto text-sm text-vimax-rose">{{ err }}</pre></div>
    <div v-if="res" class="card"><pre class="max-h-96 overflow-auto text-xs text-slate-300">{{ JSON.stringify(res, null, 2) }}</pre></div>
    <div v-if="loading" class="text-vimax-muted">Loading…</div>
  </div>
</template>
