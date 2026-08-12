import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
      },
      {
        path: 'stores',
        name: 'StoreList',
        component: () => import('../views/StoreList.vue'),
      },
      {
        path: 'stores/create',
        name: 'StoreCreate',
        component: () => import('../views/StoreEdit.vue'),
      },
      {
        path: 'stores/:id/edit',
        name: 'StoreEdit',
        component: () => import('../views/StoreEdit.vue'),
      },
      {
        path: 'crawl-logs',
        name: 'CrawlLogs',
        component: () => import('../views/CrawlLogs.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.path === '/login') {
    next()
  } else if (!token) {
    next('/login')
  } else {
    next()
  }
})

export default router
