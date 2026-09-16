/**
 * Synthetic circular orbits around a geographically fixed Earth.
 * Station coordinates are geographic; orbital heights, speed, and task choices
 * are exaggerated teaching data, not ephemerides or an optimizer result.
 *
 * Right-handed coordinates: +y is north, +z is 0° longitude, +x is 90° east.
 * A standard Three.js SphereGeometry with an equirectangular Earth texture
 * aligns to these coordinates when the Earth mesh has rotation.y = -Math.PI/2.
 * Contact eligibility never depends on the camera or station visibility.
 */
export const EARTH_RADIUS = 1;
export const GLOBE_ORBIT_PERIOD_SECONDS = 32;
export const GLOBE_LOOP_SECONDS = 64;
export const CONTACT_SLOT_SECONDS = 0.8;
export const MIN_GLOBE_CONTACT_ELEVATION_DEGREES = 12;

export interface Vector3 { x: number; y: number; z: number }
export type GlobeActionType = 'routine' | 'diagnose' | 'recover';

export interface GlobeStation extends Vector3 {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
}

export interface GlobeSatellite extends Vector3 {
  id: string;
  label: string;
  orbitId: string;
  /** Unit tangent to the orbit, in world coordinates. */
  tangent: Vector3;
  faulty: boolean;
}

export interface GlobeContact {
  stationId: string;
  satelliteId: string;
  type: GlobeActionType;
  label: string;
  /** Current geometric elevation, in degrees above the station horizon. */
  elevation: number;
  /** Slot selection score: SAT-05 priority, then midpoint elevation. */
  score: number;
}

export interface GlobeFrame {
  time: number;
  stations: GlobeStation[];
  satellites: GlobeSatellite[];
  contacts: GlobeContact[];
  status: string;
}

export interface GlobeOrbitPath { id: string; points: Vector3[] }

interface OrbitDefinition {
  id: string;
  radius: number;
  inclination: number;
  ascendingLongitude: number;
}

interface SatelliteDefinition {
  id: string;
  label: string;
  orbitId: string;
  phase: number;
}

interface ContactAssignment {
  stationId: string;
  satelliteId: string;
  score: number;
}

const TAU = 2 * Math.PI;
const radians = (degrees: number) => degrees * Math.PI / 180;
const degrees = (angle: number) => angle * 180 / Math.PI;

export function geographicToCartesian(latitude: number, longitude: number, radius = EARTH_RADIUS): Vector3 {
  const lat = radians(latitude);
  const lon = radians(longitude);
  return {
    x: radius * Math.cos(lat) * Math.sin(lon),
    y: radius * Math.sin(lat),
    z: radius * Math.cos(lat) * Math.cos(lon),
  };
}

export const globeStations: GlobeStation[] = [
  { id: 'svalbard', label: 'Svalbard', latitude: 78.2306, longitude: 15.3894 },
  { id: 'tromso', label: 'Tromsø', latitude: 69.66, longitude: 18.95 },
  { id: 'troll', label: 'Troll', latitude: -72.00215, longitude: 2.525012 },
].map((station) => ({ ...station, ...geographicToCartesian(station.latitude, station.longitude) }));

const orbits: OrbitDefinition[] = [
  { id: 'polar-1', radius: 1.42, inclination: radians(87), ascendingLongitude: radians(2) },
  { id: 'polar-2', radius: 1.55, inclination: radians(86), ascendingLongitude: radians(10) },
  { id: 'polar-3', radius: 1.63, inclination: radians(96), ascendingLongitude: radians(-35) },
  { id: 'polar-4', radius: 1.48, inclination: radians(89), ascendingLongitude: radians(65) },
];

const definitions: SatelliteDefinition[] = [
  { id: 'sat-01', label: 'SAT-01', orbitId: 'polar-1', phase: -0.15 },
  { id: 'sat-02', label: 'SAT-02', orbitId: 'polar-2', phase: 1.22 },
  { id: 'sat-03', label: 'SAT-03', orbitId: 'polar-3', phase: 2.95 },
  { id: 'sat-04', label: 'SAT-04', orbitId: 'polar-4', phase: 3.9 },
  { id: 'sat-05', label: 'SAT-05', orbitId: 'polar-1', phase: 1.36 },
  { id: 'sat-06', label: 'SAT-06', orbitId: 'polar-2', phase: 5.01 },
  { id: 'sat-07', label: 'SAT-07', orbitId: 'polar-3', phase: 0.35 },
  { id: 'sat-08', label: 'SAT-08', orbitId: 'polar-4', phase: 5.5 },
];

function orbitPoint(orbit: OrbitDefinition, phase: number): Vector3 {
  const x = orbit.radius * Math.sin(phase) * Math.cos(orbit.inclination);
  const y = orbit.radius * Math.sin(phase) * Math.sin(orbit.inclination);
  const z = orbit.radius * Math.cos(phase);
  const cosine = Math.cos(orbit.ascendingLongitude);
  const sine = Math.sin(orbit.ascendingLongitude);
  return { x: x * cosine + z * sine, y, z: -x * sine + z * cosine };
}

export const globeOrbitPaths: GlobeOrbitPath[] = orbits.map((orbit) => ({
  id: orbit.id,
  points: Array.from({ length: 193 }, (_, index) => orbitPoint(orbit, index / 192 * TAU)),
}));

function satellitesAt(time: number): GlobeSatellite[] {
  const angle = time / GLOBE_ORBIT_PERIOD_SECONDS * TAU;
  return definitions.map((definition) => {
    const orbit = orbits.find((item) => item.id === definition.orbitId)!;
    const phase = definition.phase + angle;
    const position = orbitPoint(orbit, phase);
    const derivative = orbitPoint(orbit, phase + Math.PI / 2);
    return {
      id: definition.id, label: definition.label, orbitId: definition.orbitId,
      ...position,
      tangent: { x: derivative.x / orbit.radius, y: derivative.y / orbit.radius, z: derivative.z / orbit.radius },
      faulty: definition.id === 'sat-05',
    };
  });
}

export function globeContactElevation(station: Vector3, satellite: Vector3): number {
  const dx = satellite.x - station.x;
  const dy = satellite.y - station.y;
  const dz = satellite.z - station.z;
  const range = Math.hypot(dx, dy, dz);
  const stationRadius = Math.hypot(station.x, station.y, station.z);
  if (range === 0 || stationRadius === 0) return -90;
  const sine = (dx * station.x + dy * station.y + dz * station.z) / (range * stationRadius);
  return degrees(Math.asin(Math.max(-1, Math.min(1, sine))));
}

function planSlot(start: number): ContactAssignment[] {
  const first = satellitesAt(start);
  const middle = satellitesAt(start + CONTACT_SLOT_SECONDS / 2);
  const last = satellitesAt(start + CONTACT_SLOT_SECONDS);
  const candidates: ContactAssignment[] = [];
  for (const station of globeStations) {
    for (let index = 0; index < middle.length; index += 1) {
      const elevations = [first[index], middle[index], last[index]].map((satellite) => globeContactElevation(station, satellite));
      // Circular passes have a single elevation maximum. Requiring both ends
      // above the horizon keeps this complete, short contact slot feasible.
      if (Math.min(...elevations) < MIN_GLOBE_CONTACT_ELEVATION_DEGREES) continue;
      candidates.push({
        stationId: station.id,
        satelliteId: middle[index].id,
        score: (middle[index].faulty ? 1000 : 0) + elevations[1],
      });
    }
  }
  candidates.sort((a, b) => b.score - a.score || a.stationId.localeCompare(b.stationId) || a.satelliteId.localeCompare(b.satelliteId));
  const assignedStations = new Set<string>();
  const assignedSatellites = new Set<string>();
  const selected: ContactAssignment[] = [];
  for (const candidate of candidates) {
    if (assignedStations.has(candidate.stationId) || assignedSatellites.has(candidate.satelliteId)) continue;
    selected.push(candidate);
    assignedStations.add(candidate.stationId);
    assignedSatellites.add(candidate.satelliteId);
  }
  return selected.sort((a, b) => a.stationId.localeCompare(b.stationId));
}

// Repeating, fixed-duration allocation windows prevent frame-rate-dependent
// handover chatter. Only geometry and the scene clock determine this plan.
const contactPlans = Array.from({ length: Math.round(GLOBE_LOOP_SECONDS / CONTACT_SLOT_SECONDS) }, (_, index) => planSlot(index * CONTACT_SLOT_SECONDS));

export function getGlobeFrame(elapsedSeconds: number): GlobeFrame {
  const time = Number.isFinite(elapsedSeconds)
    ? ((elapsedSeconds % GLOBE_LOOP_SECONDS) + GLOBE_LOOP_SECONDS) % GLOBE_LOOP_SECONDS
    : 0;
  const satellites = satellitesAt(time);
  const slot = Math.min(contactPlans.length - 1, Math.floor(time / CONTACT_SLOT_SECONDS + 1e-9));
  const contacts: GlobeContact[] = contactPlans[slot].flatMap((assignment) => {
    const station = globeStations.find((item) => item.id === assignment.stationId)!;
    const satellite = satellites.find((item) => item.id === assignment.satelliteId)!;
    const elevation = globeContactElevation(station, satellite);
    // Retain the actual, current horizon check even with a feasible slot plan.
    if (elevation < MIN_GLOBE_CONTACT_ELEVATION_DEGREES - 1e-9) return [];
    const type: GlobeActionType = satellite.faulty ? time < GLOBE_ORBIT_PERIOD_SECONDS ? 'diagnose' : 'recover' : 'routine';
    return [{
      ...assignment, elevation, type,
      label: type === 'diagnose' ? `Listen to ${satellite.label}` : type === 'recover' ? `Recover ${satellite.label}` : `Routine service for ${satellite.label}`,
    }];
  });
  return {
    time,
    stations: globeStations.map((station) => ({ ...station })),
    satellites,
    contacts,
    status: contacts.length
      ? contacts.map((contact) => `${globeStations.find((station) => station.id === contact.stationId)!.label}: ${contact.label}`).join(' · ')
      : 'Between ground-station passes.',
  };
}

export function getNextGlobeContactTime(elapsedSeconds: number): number {
  const start = Number.isFinite(elapsedSeconds) ? elapsedSeconds : 0;
  const signature = (frame: GlobeFrame) => frame.contacts.map((contact) => `${contact.stationId}/${contact.satelliteId}/${contact.type}`).join('|');
  const current = signature(getGlobeFrame(start));
  const firstSlot = Math.floor(start / CONTACT_SLOT_SECONDS + 1e-9);
  for (let offset = 1; offset <= contactPlans.length; offset += 1) {
    const next = (firstSlot + offset) * CONTACT_SLOT_SECONDS + 0.01;
    if (signature(getGlobeFrame(next)) !== current) return next;
  }
  return start + GLOBE_LOOP_SECONDS;
}
