/** Set a URL when a research resource is ready to publish. Null keeps its tag inactive.
 * For a public PDF, add public/paper.pdf and use `${import.meta.env.BASE_URL}paper.pdf`.
 */
export const resources: { paper: string | null; code: string | null; arxiv: string | null; supplement: string | null; website: string } = {
  paper: null,
  code: 'https://github.com/spar-mpc/spar-mpc.github.io/tree/main/solver',
  arxiv: null,
  supplement: null,
  website: 'https://github.com/spar-mpc/spar-mpc.github.io',
};

export const citation = `@article{schreiber2026sparmpc,
  title={Fault-Aware Fleet Recovery Scheduling with
         Service-Preserving Active Diagnosis},
  author={Schreiber, Carlo and Eddy, Duncan and
          Kochenderfer, Mykel J.},
  year={2026}
}`;

// Reported paper results, separate from the illustrative demo datasets.
export const campaignResults = [
  { name: 'SPAR-MPC', dwic: 35.3, recovered: 54.2 },
  { name: 'Certainty equivalent', dwic: 9.2, recovered: 14.1 },
  { name: 'Myopic VOI', dwic: 2.4, recovered: 7.9 },
  { name: 'Binary MPC', dwic: 0, recovered: 0 },
  { name: 'Threshold machine', dwic: 0, recovered: 0 },
];
