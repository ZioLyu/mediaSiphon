import { createApp } from 'vue'
import App from './App.vue'
import './styles/tokens.css'
import './styles/global.css'
import './styles/components.css'
import { bus } from './api/bus'
import { store } from './state/store'

const app = createApp(App)

bus.on((event) => store.applyEvent(event))
bus.start()

store.bootstrap().then(() => {
  app.mount('#app')
})
