/** Removes this run's build once every offline spec has finished with it. */
import { rmSync } from 'node:fs'
import { test as teardown } from '@playwright/test'
import { appDir } from './offlineApp'

teardown('remove this run’s offline build', () => {
  rmSync(appDir(), { recursive: true, force: true })
})
