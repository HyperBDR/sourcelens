import { createApp } from 'vue'

import i18n from '@/i18n'

import App from './App.vue'

import '@/assets/css/main.css'

createApp(App).use(i18n).mount('#app')
