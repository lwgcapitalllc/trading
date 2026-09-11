/** Builds the app the offline specs load (`offlineApp.ts`), once per run, before any of them start. */
import { test as setup } from '@playwright/test'
import { appDir, buildApp } from './offlineApp'

setup('build this checkout for the offline specs', async () => {
  setup.setTimeout(180_000)
  await buildApp(appDir())
})
