<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider placement="top-right">
      <n-dialog-provider>
        <n-notification-provider>
          <AppLayout />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { darkTheme, zhCN, dateZhCN } from 'naive-ui'
import AppLayout from './layout/AppLayout.vue'

const themeOverrides = {
  common: {
    primaryColor: '#4fc3f7',
    primaryColorHover: '#81d4fa',
    primaryColorPressed: '#29b6f6',
    primaryColorSuppl: '#4fc3f7',
    borderRadius: '6px',
    bodyColor: '#0a0c10',
    cardColor: '#131720',
    cardColorEmbedded: '#10141b',
    modalColor: '#141922',
    popoverColor: '#141922',
    tableColor: 'rgba(255,255,255,0.04)',
    tableHeaderColor: 'rgba(255,255,255,0.07)',
    dividerColor: 'rgba(255,255,255,0.12)',
    borderColor: 'rgba(255,255,255,0.12)',
    textColorBase: 'rgba(255,255,255,0.92)',
    textColor1: 'rgba(255,255,255,0.94)',
    textColor2: 'rgba(255,255,255,0.82)',
    textColor3: 'rgba(255,255,255,0.55)',
    successColor: '#69f0ae',
    errorColor: '#ef5350',
    warningColor: '#ffd54f',
    infoColor: '#4fc3f7',
  },
}
</script>
