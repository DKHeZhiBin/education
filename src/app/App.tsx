import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { OnboardingPage } from '../features/onboarding/OnboardingPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { StartLearningPage } from '../features/learning/StartLearningPage'
import { SimilarPracticePreviewPage } from '../features/learning/SimilarPracticePreviewPage'
import { DiagnosisPage } from '../features/learning/DiagnosisPage'
import { CoachPage } from '../features/learning/CoachPage'
import { ThoughtMapPage } from '../features/learning/ThoughtMapPage'
import { HintPage } from '../features/learning/HintPage'
import { PracticePage } from '../features/learning/PracticePage'
import { FeedbackPage } from '../features/learning/FeedbackPage'
import { MistakesPage } from '../features/review/MistakesPage'
import { ProgressPage } from '../features/review/ProgressPage'
import { ProfilePage } from '../features/profile/ProfilePage'
import { AuthPage } from '../features/auth/AuthPage'
import { KnowledgePlanetPage } from '../features/knowledge/KnowledgePlanetPage'
import { ThinkingMethodsPage } from '../features/knowledge/ThinkingMethodsPage'
import { ThinkingMethodDetailPage } from '../features/knowledge/ThinkingMethodDetailPage'
import { KnowledgePointDetailPage } from '../features/knowledge/KnowledgePointDetailPage'
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
      <Route path="/learn/:sessionId/similar" element={<Page><SimilarPracticePreviewPage /></Page>} />
      <Route path="/learn/:sessionId/diagnosis" element={<Page><DiagnosisPage /></Page>} />
      <Route path="/learn/:sessionId/coach" element={<Page><CoachPage /></Page>} />
      <Route path="/learn/:sessionId/map" element={<Page><ThoughtMapPage /></Page>} />
      <Route path="/learn/:sessionId/hints" element={<Page><HintPage /></Page>} />
      <Route path="/learn/:sessionId/practice" element={<Page><PracticePage /></Page>} />
      <Route path="/learn/:sessionId/feedback" element={<Page><FeedbackPage /></Page>} />
      <Route path="/learn/diagnosis" element={<Page><DiagnosisPage /></Page>} />
      <Route path="/learn/coach" element={<Page><CoachPage /></Page>} />
      <Route path="/learn/practice" element={<Page><PracticePage /></Page>} />
      <Route path="/learn/feedback" element={<Page><FeedbackPage /></Page>} />
      <Route path="/mistakes" element={<Page><MistakesPage /></Page>} />
      <Route path="/progress" element={<Page><ProgressPage /></Page>} />
      <Route path="/knowledge" element={<Page><KnowledgePlanetPage /></Page>} />
      <Route path="/knowledge/methods" element={<Page><ThinkingMethodsPage /></Page>} />
      <Route path="/knowledge/methods/:methodId" element={<Page><ThinkingMethodDetailPage /></Page>} />
      <Route path="/knowledge/points/:knowledgeCode" element={<Page><KnowledgePointDetailPage /></Page>} />
      <Route path="/profile" element={<Page><ProfilePage /></Page>} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  )
}
