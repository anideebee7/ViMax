import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: parseInt(env.VITE_PORT || '5173', 10),
      proxy: env.VITE_API_PROXY
        ? { '/api': { target: env.VITE_API_PROXY, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') } }
        : undefined,
    },
  };
});
