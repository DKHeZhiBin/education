import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { OnboardingPage } from '../features/onboarding/OnboardingPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { StartLearningPage } from '../features/learning/StartLearningPage'
import { DiagnosisPage } from '../features/learning/DiagnosisPage'
import { CoachPage } from '../features/learning/CoachPage'
import { PracticePage } from '../features/learning/PracticePage'
import { FeedbackPage } from '../features/learning/FeedbackPage'
import { MistakesPage } from '../features/review/MistakesPage'
import { ProgressPage } from '../features/review/ProgressPage'
import { ProfilePage } from '../features/profile/ProfilePage'
import { AuthPage } from '../features/auth/AuthPage'
import { hasAccessToken } from '../services/auth'

function Page({ children }: { children: ReactNode }) {
  if (!hasAccessToken()) return <Navigate to="/auth" replace />
  return <AppShell>{children}</AppShell>
}

function Protected({ children }: { children: ReactNode }) {
  return hasAccessToken() ? children : <Navigate to="/auth" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={hasAccessToken() ? '/home' : '/auth'} replace />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route path="/onboarding" element={<Protected><OnboardingPage /></Protected>} />
      <Route path="/home" element={<Page><DashboardPage /></Page>} />
      <Route path="/learn/new" element={<Page><StartLearningPage /></Page>} />
      <Route path="/learn/:sessionId/diagnosis" element={<Page><DiagnosisPage /></Page>} />
      <Route path="/learn/:sessionId/coach" element={<Page><CoachPage /></Page>} />
      <Route path="/learn/:sessionId/practice" element={<Page><PracticePage /></Page>} />
      <Route path="/learn/:sessionId/feedback" element={<Page><FeedbackPage /></Page>} />
      <Route path="/learn/diagnosis" element={<Page><DiagnosisPage /></Page>} />
      <Route path="/learn/coach" element={<Page><CoachPage /></Page>} />
      <Route path="/learn/practice" element={<Page><PracticePage /></Page>} />
      <Route path="/learn/feedback" element={<Page><FeedbackPage /></Page>} />
      <Route path="/mistakes" element={<Page><MistakesPage /></Page>} />
      <Route path="/progress" element={<Page><ProgressPage /></Page>} />
      <Route path="/profile" element={<Page><ProfilePage /></Page>} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  )
}
