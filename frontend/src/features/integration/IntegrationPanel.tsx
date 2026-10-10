import { OpportunityWorkbench } from './OpportunityWorkbench'
import { ProductAccess } from './ProductAccess'
import './discovery.css'

export default function IntegrationPanel() {
  return <section className="feature-section">
    <OpportunityWorkbench />
    <details className="panel"><summary>Earlier experiment · SourceTable v1</summary>
      <p>Preserved integration evidence. This is an earlier candidate, not the selected result of the new discovery flow.</p>
      <ProductAccess />
    </details>
  </section>
}
