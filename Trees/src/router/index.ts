import { createRouter, createWebHistory } from 'vue-router'
import BreederLayout from '../views/BreederLayout.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: BreederLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
        },
        {
          path: 'data',
          name: 'data',
          component: () => import('../views/DataManagementView.vue'),
        },
        {
          path: 'segmentation',
          name: 'segmentation',
          component: () => import('../views/TreeSegmentationView.vue'),
        },
        {
          path: 'phenotype',
          name: 'phenotype',
          component: () => import('../views/PhenotypeView.vue'),
        },
        {
          path: 'genetic',
          name: 'genetic',
          component: () => import('../views/GeneticAnalysisView.vue'),
        },
        {
          path: 'selection',
          name: 'selection',
          component: () => import('../views/SelectionView.vue'),
        },
        {
          path: 'visualization',
          name: 'visualization',
          component: () => import('../views/VisualizationView.vue'),
        },
      ],
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('../views/AboutView.vue'),
    },
  ],
})

export default router
