/**
 * Vite config. chess.js + cm-chessboard are imported as ESM modules
 * (js/playable-board.js); cm-chessboard static assets
 * (chessboard.css, extensions, pieces/staunty.svg) are copied to
 * public/cm-chessboard/ by the prebuild/predev scripts (package.json)
 * from node_modules/cm-chessboard/assets.
 *
 * Note: `vite-plugin-pwa` had been installed in anticipation of phase 4
 * (chunking + Service Worker) but was never imported here; it has been
 * removed from devDependencies. Reinstall it if the SW is enabled.
 */
import { defineConfig } from 'vite';

export default defineConfig({
    root: '.',
    base: './',
    build: {
        outDir: 'dist',
        sourcemap: true,
        target: 'es2020',
        // data/ doit rester accessible au runtime (fetch)
        assetsInlineLimit: 0,
    },
    server: {
        port: 5173,
        host: '127.0.0.1',
        open: false,
    },
    test: {
        environment: 'node',
        include: ['tests/**/*.test.js'],
    },
});
