import {build} from 'vite';
await build({configFile:false,build:{cssCodeSplit:false,rollupOptions:{output:{entryFileNames:'app.js',chunkFileNames:'chunk-[hash].js',assetFileNames:'style.css'}}}});
