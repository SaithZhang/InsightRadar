import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({plugins:[vue()],server:{host:'127.0.0.1',port:15173,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18080'}}},preview:{host:'127.0.0.1',port:15173,proxy:{'/api':{target:'http://127.0.0.1:18080'}}},build:{chunkSizeWarningLimit:1600}})
