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

/**
 * Fichiers sensibles ne devant jamais être servis par HTTP,
 * même si la racine source (index.html + configs) est exposée.
 * En prod seul `dist/` est servi par Nginx (voir nginx.conf),
 * mais `vite dev` sert la racine par défaut — ce plugin bouche ce trou.
 */
const SENSITIVE_PATHS = [
    '/package.json',
    '/package-lock.json',
    '/vite.config.js',
    '/Dockerfile',
    '/nginx.conf',
    '/.dockerignore',
];

function denySensitiveFiles() {
    return {
        name: 'deny-sensitive-files',
        configureServer(server) {
            server.middlewares.use((req, res, next) => {
                const pathname = (req.url || '/').split('?')[0].split('#')[0];
                const blocked =
                    SENSITIVE_PATHS.some(
                        (p) => pathname === p || pathname.startsWith(p + '/')
                    ) ||
                    pathname.startsWith('/.git') ||
                    pathname.startsWith('/tests/') ||
                    pathname.includes('.env');
                if (blocked) {
                    res.statusCode = 404;
                    res.end('Not found');
                    return;
                }
                next();
            });
        },
    };
}

export default defineConfig({
    root: '.',
    base: './',
    plugins: [denySensitiveFiles()],
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
