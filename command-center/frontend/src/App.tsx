import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Sidebar } from '@/components/Sidebar'
import { TopBar } from '@/components/TopBar'
import { Overview } from '@/pages/Overview'
import { SmartMoney } from '@/pages/SmartMoney'
import { Bots } from '@/pages/Bots'
import { Calendar } from '@/pages/Calendar'
import { Strategies } from '@/pages/Strategies'
import { Rulesets } from '@/pages/Rulesets'
import { Backtests } from '@/pages/Backtests'
import { BacktestDetail } from '@/pages/BacktestDetail'
import { StrategyDetail } from '@/pages/StrategyDetail'
import { SweepDetail } from '@/pages/SweepDetail'
import { StackDetail } from '@/pages/StackDetail'
import { Optimizations } from '@/pages/Optimizations'
import { OptimizationDetail } from '@/pages/OptimizationDetail'
import { TuningWorkbench } from '@/pages/TuningWorkbench'
import { StressTests } from '@/pages/StressTests'
import StressTestDetail from '@/pages/StressTestDetail'
import { Settings } from '@/pages/Settings'
import { FEATURES } from '@/lib/features'

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
              {/* Routes and nav items move together — a page with no way to reach
                  it is still reachable by URL, which is not "removed". */}
              {FEATURES.smartMoney && (
                <>
                  <Route path="/smart-money"              element={<SmartMoney />} />
                  <Route path="/smart-money/:runId/candidates/:id" element={<SmartMoney />} />
                </>
              )}
              <Route path="/bots"                     element={<Bots />} />
              <Route path="/calendar"                 element={<Calendar />} />
              <Route path="/strategies"                             element={<Strategies />} />
              <Route path="/rulesets"                               element={<Rulesets />} />
              <Route path="/backtests"                              element={<Backtests />} />
              <Route path="/backtests/runs/:runId"              element={<BacktestDetail />} />
              <Route path="/strategies/:strategyId"            element={<StrategyDetail />} />
              <Route path="/backtests/sweeps/:sweepId"         element={<SweepDetail />} />
              <Route path="/backtests/stacks/:stackId"         element={<StackDetail />} />
              <Route path="/optimizations"                      element={<Optimizations />} />
              <Route path="/optimizations/:optimizationId"      element={<OptimizationDetail />} />
              <Route path="/backtests/runs/:runId/tune"         element={<TuningWorkbench />} />
              <Route path="/backtests/stress-tests/:stressTestId" element={<StressTestDetail />} />
              <Route path="/stress-tests"                       element={<StressTests />} />
              <Route path="/stress-tests/:stressTestId"         element={<StressTestDetail />} />
              <Route path="/settings"                 element={<Settings />} />
              {/* An unmatched path rendered nothing at all — a blank main area beside
                  a working sidebar, which reads as the app breaking. A bookmark to a
                  flagged-off page (or any typo) lands on the Overview instead. */}
              <Route path="*"                         element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
