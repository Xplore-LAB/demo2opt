import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Home from '../views/Home.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard
  },
  {
    path: '/analysis',
    name: 'Home',
    component: Home
  },
  {
    path: '/pi-analysis',
    name: 'PIAnalysis',
    component: () => import('../views/PIAnalysis.vue')
  },
  {
    path: '/nitrogen-plug-demo',
    name: 'NitrogenPlugDemo',
    component: () => import('../views/NitrogenPlugDemo.vue')
  },
  {
    path: '/fault-tree',
    name: 'FaultTree',
    component: () => import('../views/FaultTreePage.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
