import { useEffect, useRef, useState } from 'react';
import { GLOBE_LOOP_SECONDS, getGlobeFrame, globeOrbitPaths } from '../data/globeDemo';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { OrbitScene } from './OrbitScene';
import type { SceneSnapshot } from './OrbitScene';
import '../styles/fleet.css';

const contactLabels = { routine: 'Routine', diagnose: 'Diagnose', recover: 'Recover' };
const positionText = (point: { x: number; y: number; z: number }) => [point.x, point.y, point.z].map((value) => value.toFixed(5)).join(',');

function FallbackGlobe({ time }: { time: number }) {
  const frame = getGlobeFrame(time);
  const camera = { x: .218, y: .5, z: .838 };
  const length = Math.hypot(camera.x, camera.y, camera.z);
  const forward = { x: camera.x / length, y: camera.y / length, z: camera.z / length };
  const horizontal = Math.hypot(forward.x, forward.z);
  const right = { x: forward.z / horizontal, y: 0, z: -forward.x / horizontal };
  const up = { x: forward.y * right.z, y: forward.z * right.x - forward.x * right.z, z: -forward.y * right.x };
  const project = (point: { x: number; y: number; z: number }) => {
    const x = point.x * right.x + point.y * right.y + point.z * right.z;
    const y = -(point.x * up.x + point.y * up.y + point.z * up.z);
    const z = point.x * forward.x + point.y * forward.y + point.z * forward.z;
    return { x, y, visible: z >= 0 || Math.hypot(x, y) >= 1 };
  };
  return <svg className="globe-fallback" viewBox="-2.25 -1.7 4.5 3.4" role="img" aria-label="Schematic Earth and satellite fleet. The 3D renderer is unavailable.">
    <g fill="none" stroke="#d4d4d4" strokeWidth=".007">{globeOrbitPaths.map((orbit) => <polyline key={orbit.id} points={orbit.points.map((point) => { const p = project(point); return `${p.x},${p.y}`; }).join(' ')} />)}</g>
    <circle r="1" fill="#f1f3f4" stroke="#aab7bf" strokeWidth=".009" />
    <g fill="none" stroke="#d0d9df" strokeWidth=".007"><ellipse rx=".42" ry="1" /><ellipse rx=".78" ry="1" /><path d="M-1 0H1M-.86-.5Q0-.72.86-.5M-.86.5Q0 .72.86.5" /></g>
    {frame.contacts.map((contact) => {
      const satellite = project(frame.satellites.find((item) => item.id === contact.satelliteId)!);
      const station = project(frame.stations.find((item) => item.id === contact.stationId)!);
      return station.visible && satellite.visible ? <line key={contact.stationId} x1={station.x} y1={station.y} x2={satellite.x} y2={satellite.y} className={`globe-fallback-link globe-fallback-link--${contact.type}`} strokeWidth=".01" /> : null;
    })}
    {frame.satellites.map((satellite) => {
      const point = project(satellite);
      return point.visible ? <g key={satellite.id} transform={`translate(${point.x} ${point.y})`} stroke="#567286" strokeWidth=".013" fill="#fff"><path d="M-.1-.04h.065v.08H-.1ZM.035-.04H.1v.08H.035Z" /><rect x="-.025" y="-.055" width=".05" height=".11" /></g> : null;
    })}
    {frame.stations.map((station) => { const point = project(station); return point.visible ? <g key={station.id}><circle cx={point.x} cy={point.y} r=".025" fill="#333" stroke="#fff" strokeWidth=".009" /></g> : null; })}
  </svg>;
}

export default function FleetDemo() {
  const reducedMotion = useReducedMotion();
  const figureRef = useRef<HTMLDivElement>(null);
  const canvasHost = useRef<HTMLDivElement>(null);
  const scene = useRef<OrbitScene | null>(null);
  const [renderer, setRenderer] = useState<'loading' | 'webgl' | 'fallback'>('loading');
  const [snapshot, setSnapshot] = useState<SceneSnapshot | null>(null);
  const [inView, setInView] = useState(false);
  const [tabVisible, setTabVisible] = useState(() => typeof document === 'undefined' || !document.hidden);
  const [fallbackTime, setFallbackTime] = useState(0);
  const time = renderer === 'fallback' ? fallbackTime : snapshot?.time ?? 0;
  const frame = renderer === 'fallback' ? getGlobeFrame(fallbackTime) : snapshot?.frame ?? getGlobeFrame(0);
  const inspectedId = snapshot?.inspectedId;
  const visibleStations = new Set(snapshot?.stations.filter((station) => station.visible).map((station) => station.id));
  const visibleContacts = renderer === 'fallback' ? frame.contacts : frame.contacts.filter((contact) => visibleStations.has(contact.stationId));
  const primaryContact = visibleContacts.find((contact) => contact.type !== 'routine') ?? visibleContacts[0];
  const contactText = primaryContact
    ? `${frame.stations.find((station) => station.id === primaryContact.stationId)?.label} → ${frame.satellites.find((satellite) => satellite.id === primaryContact.satelliteId)?.label} · ${contactLabels[primaryContact.type]}`
    : frame.contacts.length ? 'Ground contacts on the far side' : 'Between ground contacts';

  useEffect(() => {
    const host = canvasHost.current;
    if (!host) return;
    try {
      const instance = new OrbitScene(host, setSnapshot);
      scene.current = instance;
      setRenderer('webgl');
      return () => { instance.dispose(); if (scene.current === instance) scene.current = null; };
    } catch {
      host.replaceChildren();
      setRenderer('fallback');
    }
  }, []);

  useEffect(() => {
    const figure = figureRef.current;
    if (!figure) return;
    if (!('IntersectionObserver' in window)) { setInView(true); return; }
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting && entry.intersectionRatio >= .15), { threshold: [0, .15] });
    observer.observe(figure);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const update = () => setTabVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  useEffect(() => { scene.current?.setRunning(!reducedMotion); }, [reducedMotion, renderer]);
  useEffect(() => { scene.current?.setVisible(inView && tabVisible); }, [inView, tabVisible, renderer]);

  useEffect(() => {
    if (renderer !== 'fallback' || reducedMotion || !inView || !tabVisible) return;
    let request: number;
    let previous: number | null = null;
    const advance = (now: number) => {
      if (previous !== null) {
        const elapsed = Math.min((now - previous) / 1000, .1);
        setFallbackTime((value) => (value + elapsed) % GLOBE_LOOP_SECONDS);
      }
      previous = now;
      request = requestAnimationFrame(advance);
    };
    request = requestAnimationFrame(advance);
    return () => cancelAnimationFrame(request);
  }, [renderer, reducedMotion, inView, tabVisible]);

  return <div className="orbit-figure" ref={figureRef} role="group" aria-label="Orbit animation">
    <div className="globe-scene" data-renderer={renderer} data-texture={renderer === 'fallback' ? 'unavailable' : snapshot?.texture ?? 'loading'} data-animation-time={time.toFixed(3)} data-camera-position={snapshot?.camera ?? 'overview'}>
      <div className="globe-canvas-host" ref={canvasHost} />
      {renderer === 'fallback' && <FallbackGlobe time={fallbackTime} />}
      <span className="globe-navigation-hint">{renderer === 'fallback' ? 'Schematic view · 3D unavailable' : 'Drag to rotate'}</span>
      {renderer === 'webgl' && snapshot?.satellites.filter((satellite) => satellite.visible && satellite.id === (inspectedId ?? primaryContact?.satelliteId)).map((satellite) => <span className="globe-satellite-label" key={satellite.id} style={{ left: satellite.x, top: satellite.y }} aria-hidden="true">{satellite.label.replace(/^SAT-?/, '')}</span>)}
      <div className={`globe-contact-label${primaryContact ? ` globe-contact-label--${primaryContact.type}` : ''}`} data-current-contact="true">{contactText}</div>
    </div>
    <div className="orbit-legend" aria-label="Contact types"><span><i />Routine</span><span><i className="orbit-key-diagnose" />Diagnose</span><span><i className="orbit-key-recover" />Recover</span></div>
    <div className="globe-accessible-state" aria-label="Current spacecraft and contact state">
      {frame.satellites.map((satellite) => <span key={satellite.id} data-satellite-id={satellite.id} data-position={positionText(satellite)} data-orientation={snapshot?.satellites.find((item) => item.id === satellite.id)?.orientation ?? positionText(satellite.tangent)}>{satellite.label}; {frame.contacts.find((contact) => contact.satelliteId === satellite.id)?.label ?? 'no ground contact'}. </span>)}
      {frame.contacts.map((contact) => <span key={`${contact.stationId}-${contact.satelliteId}`} data-contact-for={contact.satelliteId} data-station-id={contact.stationId} data-contact-type={contact.type} data-elevation={contact.elevation}>{contact.label}; {contact.stationId}; elevation {contact.elevation.toFixed(1)} degrees. </span>)}
    </div>
  </div>;
}
