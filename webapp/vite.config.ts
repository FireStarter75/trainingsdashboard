import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// base './' zodat de build onder elke prefix werkt (productie / en test /test);
// de Flaska-route serveert de build op /app.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist' },
});
