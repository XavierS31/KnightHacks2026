import { lazy, Suspense, useState } from 'react'
import { AsyncState } from './shared/AsyncState'

const IntegrationPanel = lazy(() => import('./features/integration/IntegrationPanel'))
const PersonaPanel = lazy(() => import('./features/personas/PersonaPanel'))
const EvolutionPanel = lazy(() => import('./features/evolution/EvolutionPanel'))

const phases = [
  { name: 'Integration', detail: 'Discover & validate', owner: 'Developer A' },
  { name: 'Personas', detail: 'Observe real trials', owner: 'Developer B' },
  { name: 'Evolution', detail: 'Improve & compare', owner: 'Developer C' },
]

export default function App() {
  const [phase, setPhase] = useState(0)
  return <div className="workspace">
    <aside className="sidebar">
      <a href="#main" className="brand">RepoFusion<span>Experiment workspace</span></a>
      <div className="sidebar-label">THREE PHASES · ONE PRODUCT</div>
      <nav aria-label="Project phases">{phases.map((item, index) =>
        <button key={item.name} className={`phase-link ${phase === index ? 'active' : ''}`}
          aria-current={phase === index ? 'page' : undefined} onClick={() => setPhase(index)}>
          <span className="phase-number">0{index + 1}</span>
          <span><strong>{item.name}</strong><small>{item.detail}</small></span>
        </button>)}</nav>
      <div className="sidebar-footer"><span className="status-dot" /> Shared scaffold
        <p>Hugging Face inference<br />Neon persistence<br />Playwright execution</p></div>
    </aside>
    <main id="main">
      <header className="topbar"><span>{phases[phase].owner} / full-stack ownership</span><span>v0.1 · Foundation</span></header>
      <div className="content">
        <div className="eyebrow">REPOSITORIES → TRIALS → IMPROVEMENTS</div>
        <h1>{phases[phase].name}</h1>
        <p className="intro">An evidence trail from complementary code to a tested product.</p>
        <div className="fixture-notice" role="note"><strong>Development scaffold</strong>
          <span>Sample records are labeled fixtures. Configured personas and illustrative suggestions are not executed results.</span></div>
        <Suspense fallback={<AsyncState error={null} />}>
          {phase === 0 ? <IntegrationPanel /> : phase === 1 ? <PersonaPanel /> : <EvolutionPanel />}
        </Suspense>
      </div>
    </main>
  </div>
}
