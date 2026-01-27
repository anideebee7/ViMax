import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';
import BrandsGamesView from '../views/BrandsGamesView.vue';
import CharactersView from '../views/CharactersView.vue';
import PipelinesView from '../views/PipelinesView.vue';
import TasksView from '../views/TasksView.vue';
import UtilsView from '../views/UtilsView.vue';

const routes = [
  { path: '/', name: 'Home', component: HomeView },
  { path: '/brands-games', name: 'BrandsGames', component: BrandsGamesView },
  { path: '/characters', name: 'Characters', component: CharactersView },
  { path: '/pipelines', name: 'Pipelines', component: PipelinesView },
  { path: '/tasks', name: 'Tasks', component: TasksView },
  { path: '/utils', name: 'Utils', component: UtilsView },
];

export default createRouter({ history: createWebHistory(), routes });
