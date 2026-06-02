import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Sidebar } from '@/components/Sidebar'
import { TopBar } from '@/components/TopBar'
import { Overview } from '@/pages/Overview'
import { SmartMoney } from '@/pages/SmartMoney'
import { Bots } from '@/pages/Bots'
import { Backtests } from '@/pages/Backtests'
import { BacktestDetail } from '@/pages/BacktestDetail'
import { StrategyDetail } from '@/pages/StrategyDetail'
import { SweepDetail } from '@/pages/SweepDetail'
import { OptimizationDetail } from '@/pages/OptimizationDetail'
import { StressTests } from '@/pages/StressTests'
import StressTestDetail from '@/pages/StressTestDetail'
import { Settings } from '@/pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="bottom-right"
        theme="dark"
        richColors
        toastOptions={{ style: { fontFamily: 'inherit', fontSize: '13px' } }}
      />
      <div className="flex h-screen overflow-hidden bg-bg-base text-text-primary">
        <Sidebar />
        <div className="flex flex-col flex-1 min-w-0">
          <TopBar />
          <main className="flex-1 overflow-y-auto p-[22px]">
            <Routes>
              <Route path="/"                         element={<Overview />} />
              <Route path="/smart-money"              element={<SmartMoney />} />
              <Route path="/smart-money/:runId/candidates/:id" element={<SmartMoney />} />
              <Route path="/bots"                     element={<Bots />} />
              <Route path="/backtests"                              element={<Backtests />} />
              <Route path="/backtests/runs/:runId"              element={<BacktestDetail />} />
              <Route path="/backtests/strategies/:strategyId"  element={<StrategyDetail />} />
              <Route path="/backtests/sweeps/:sweepId"         element={<SweepDetail />} />
              <Route path="/backtests/optimizations/:optimizationId" element={<OptimizationDetail />} />
              <Route path="/backtests/stress-tests/:stressTestId" element={<StressTestDetail />} />
              <Route path="/stress-tests"                       element={<StressTests />} />
              <Route path="/stress-tests/:stressTestId"         element={<StressTestDetail />} />
              <Route path="/settings"                 element={<Settings />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
