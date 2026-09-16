import { lazy, Suspense } from 'react';
import Citation from './components/Citation';
import Icon from './components/Icon';
import Optimization from './components/Optimization';
import ResourceLink from './components/ResourceLink';
import Results from './components/Results';
import { resources } from './data/site';

const FleetDemo = lazy(() => import('./demos/FleetDemo'));

export default function App() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <main id="main">
        <header className="hero">
          <p className="project-name">SPAR-MPC</p>
          <h1 className="paper-title">
            Fault-Aware Fleet Recovery Scheduling<br className="desktop-break" />{' '}
            with Service-Preserving Active Diagnosis
          </h1>
          <p className="authors">
            <span>Carlo Schreiber,</span>{' '}
            <span>Duncan Eddy,</span>{' '}
            <span>Mykel J. Kochenderfer</span>
          </p>
          <p className="affiliation">Stanford University</p>
          <nav className="hero-links" aria-label="Research resources">
            <ResourceLink label="arXiv" href={resources.arxiv} icon="paper" />
            <ResourceLink label="Code" href={resources.code} icon="code" />
            <a href="#citation"><Icon name="copy" /><span>BibTeX</span></a>
          </nav>
        </header>

        <section className="fleet-section content-width" id="fleet" aria-label="Interactive fleet recovery example">
          <Suspense fallback={<div className="globe-loading" role="status">Loading globe…</div>}>
            <FleetDemo />
          </Suspense>
        </section>

        <section className="abstract-section" id="abstract" aria-labelledby="abstract-title">
          <div className="reading-width">
            <h2 id="abstract-title">Abstract</h2>
            <p className="method-summary">
              Remotely operated robotic fleets must diagnose and recover from system faults
              using limited communication opportunities, yet different faults can produce
              similar observations while requiring different interventions. We introduce
              Service-Preserving Active Recovery Model Predictive Control (SPAR-MPC), a
              receding-horizon controller that jointly schedules fault-aware active diagnosis
              and recovery. We evaluate SPAR-MPC on a satellite launch and early-operations
              scenario, where deadline-weighted intervention completion rises from 9.2% at
              most for four baseline controllers to 35.3%, and lethal recovery from 14% to 54%.
              This improvement comes primarily from allocating limited communication time to
              recovery actions that account for the likely fault and its intervention deadline.
              Scheduling additional observations to determine which recovery action is needed
              becomes important when communication time is scarce: in a two-asset study with
              one contested recovery opportunity, it increases deadline-weighted intervention
              completion from 37.5% to 78.6%. These results show that awareness of failure modes
              enables effective recovery scheduling, while active diagnosis matters when
              ambiguity and communication capacity constrain which faults can be recovered.
            </p>
          </div>
        </section>

        <Optimization />
        <Results />
        <div className="reading-width">
          <Citation />
        </div>
        <div className="footer-band">
          <footer className="site-footer reading-width">
            <span>Stanford University, 2026</span>
            <span>Layout inspired by <a href="https://github.com/nerfies/nerfies.github.io" target="_blank" rel="noopener noreferrer">Nerfies</a></span>
            <a href={resources.website} target="_blank" rel="noopener noreferrer">Website source</a>
          </footer>
        </div>
      </main>
    </>
  );
}
