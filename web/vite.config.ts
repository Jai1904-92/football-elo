import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Served from https://<user>.github.io/football-elo/ (override with BASE=/ for a custom domain)
export default defineConfig({
  base: process.env.BASE ?? '/football-elo/',
  plugins: [react()],
});
