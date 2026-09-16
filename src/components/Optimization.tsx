export default function Optimization() {
  return (
    <section className="section formulation-section" id="method" aria-labelledby="method-title">
      <div className="reading-width">
        <h2 id="method-title">Optimization Problem</h2>
        <p className="section-intro">
          In a fleet, diagnosing one vehicle can use time needed to recover another.
          SPAR-MPC first plans routine operations and recovery to maximize expected service
          across sampled fault scenarios, respecting resource limits, vehicle priorities,
          and recovery deadlines. It then selects diagnostics that can improve later recovery
          decisions, while preserving the plan’s sampled service value and keeping follow-up
          actions feasible. The controller executes the next actions and replans as new
          observations arrive.
        </p>
      </div>
    </section>
  );
}
