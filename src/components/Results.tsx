import { useState } from 'react';
import { campaignResults } from '../data/site';

type Metric = 'dwic' | 'recovered';

export default function Results() {
  const [metric, setMetric] = useState<Metric>('recovered');
  const isCompletion = metric === 'dwic';
  const maximum = isCompletion ? 40 : 60;

  return (
    <section className="section results-section" id="results" aria-labelledby="results-title">
      <div className="reading-width">
      <h2 id="results-title">Validation on Satellite Fleet</h2>
      <p className="section-intro">
        We validate SPAR-MPC in simulated satellite launch and early operations (LEOP):
        100 satellites, 48 hours, and one shared ground station. Results are averaged over
        100 matched trials.
      </p>
      <figure className="results-figure">
        <div className="figure-tabs" role="group" aria-label="Result metric">
          <button aria-pressed={!isCompletion} onClick={() => setMetric('recovered')}>Lethal recovery</button>
          <button aria-pressed={isCompletion} onClick={() => setMetric('dwic')}>Deadline-weighted completion</button>
        </div>
        <div className="chart-rows" aria-live="polite" aria-label={isCompletion ? 'Deadline-weighted intervention completion' : 'Lethal faults recovered'}>
          {campaignResults.map(result => {
            const value = result[metric];
            return (
              <div className={`chart-row${result.name === 'SPAR-MPC' ? ' chart-ours' : ''}`} key={result.name}>
                <span className="chart-label">{result.name}</span>
                <div className="chart-track">
                  <div className="chart-bar" style={{ width: `${value / maximum * 100}%` }} />
                </div>
                <span className="chart-value">{value.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
        <div className="chart-axis" aria-hidden="true">
          {[0, 1, 2, 3, 4].map(tick => <span key={tick}>{tick * maximum / 4}{tick === 4 ? '%' : ''}</span>)}
        </div>
        <figcaption>
          {isCompletion
            ? 'Completion is weighted by how early the correct recovery finishes; late or unsuccessful recoveries receive zero.'
            : 'Fraction of lethal faults successfully recovered before their deadlines.'}
          <span className="source-note">Table I</span>
        </figcaption>
      </figure>
      </div>
    </section>
  );
}
