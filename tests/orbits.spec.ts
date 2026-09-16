import { expect, test } from '@playwright/test';
import { EARTH_RADIUS, GLOBE_LOOP_SECONDS, MIN_GLOBE_CONTACT_ELEVATION_DEGREES, geographicToCartesian, globeStations, getGlobeFrame } from '../src/data/globeDemo';

test('KSAT station coordinates map correctly onto the globe', () => {
  expect(globeStations.map(station => station.id)).toEqual(['svalbard', 'tromso', 'troll']);
  for (const station of globeStations) {
    expect(Math.hypot(station.x, station.y, station.z)).toBeCloseTo(EARTH_RADIUS, 10);
    expect(Math.asin(station.y / EARTH_RADIUS) * 180 / Math.PI).toBeCloseTo(station.latitude, 8);
    expect(Math.atan2(station.x, station.z) * 180 / Math.PI).toBeCloseTo(station.longitude, 8);
  }
  const greenwich = geographicToCartesian(0, 0);
  expect(greenwich.x).toBeCloseTo(0);
  expect(greenwich.y).toBeCloseTo(0);
  expect(greenwich.z).toBeCloseTo(1);
  expect(geographicToCartesian(90, 0).y).toBeCloseTo(1);
  expect(geographicToCartesian(0, 90).x).toBeCloseTo(1);
  expect(globeStations[0].latitude).toBeCloseTo(78.23, 1);
  expect(globeStations[1].latitude).toBeCloseTo(69.66, 1);
  expect(globeStations[2].latitude).toBeCloseTo(-72, 1);
});

test('contacts stay above the horizon, respect capacity, and reach all three stations', () => {
  const assignments = new Set<string>();
  const actions = new Set<string>();
  const served = new Set<string>();
  for (let time = 0; time < GLOBE_LOOP_SECONDS; time += 0.125) {
    const frame = getGlobeFrame(time);
    expect(new Set(frame.contacts.map(contact => contact.stationId)).size).toBe(frame.contacts.length);
    expect(new Set(frame.contacts.map(contact => contact.satelliteId)).size).toBe(frame.contacts.length);
    assignments.add(frame.contacts.map(contact => `${contact.stationId}/${contact.satelliteId}`).join('|'));
    for (const contact of frame.contacts) {
      const station = frame.stations.find(item => item.id === contact.stationId)!;
      const satellite = frame.satellites.find(item => item.id === contact.satelliteId)!;
      const direction = [satellite.x - station.x, satellite.y - station.y, satellite.z - station.z];
      // Recompute geometric elevation independently of the model's helper.
      const radialDot = direction[0] * station.x + direction[1] * station.y + direction[2] * station.z;
      const sineElevation = radialDot / (Math.hypot(...direction) * EARTH_RADIUS);
      expect(Math.asin(sineElevation) * 180 / Math.PI).toBeGreaterThanOrEqual(MIN_GLOBE_CONTACT_ELEVATION_DEGREES - 1e-9);
      // A positive radial derivative means the complete link leaves the sphere.
      expect(radialDot).toBeGreaterThan(0);
      actions.add(contact.type);
      served.add(contact.stationId);
    }
  }
  expect(assignments.size).toBeGreaterThan(8);
  expect([...served].sort()).toEqual(['svalbard', 'troll', 'tromso']);
  expect([...actions].sort()).toEqual(['diagnose', 'recover', 'routine']);
  expect(getGlobeFrame(GLOBE_LOOP_SECONDS)).toEqual(getGlobeFrame(0));
});
