import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { usePreferencesStore } from './store/preferences'
import './assets/css/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

const preferencesStore = usePreferencesStore()
preferencesStore.loadFromLocalStorage()

app.mount('#app')
