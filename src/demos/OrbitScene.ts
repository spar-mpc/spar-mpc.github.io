import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  GLOBE_LOOP_SECONDS, getGlobeFrame, getNextGlobeContactTime, globeOrbitPaths, globeStations,
} from '../data/globeDemo';

export type GlobeFrame = ReturnType<typeof getGlobeFrame>;
export type SceneLabel = { id: string; label: string; x: number; y: number; visible: boolean };
export type SceneSnapshot = {
  time: number;
  frame: GlobeFrame;
  stations: SceneLabel[];
  satellites: (SceneLabel & { orientation: string })[];
  camera: string;
  inspectedId: string | null;
  selectedId: string | null;
  texture: 'loading' | 'ready' | 'error';
};

const colors = { routine: 0x969696, diagnose: 0x476c85, recover: 0x8c1515 };
const cameraDistance = 6;
const initialCamera = new THREE.Vector3(.218, .5, .838).normalize().multiplyScalar(cameraDistance);
const vector = (value: { x: number; y: number; z: number }) => new THREE.Vector3(value.x, value.y, value.z);

/** Owns the only simulation clock; camera navigation can also render while paused. */
export class OrbitScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(34, 1, .05, 40);
  private controls: OrbitControls;
  private earth: THREE.Mesh;
  private satellites = new Map<string, THREE.Group>();
  private links = new Map<string, { line: THREE.Line; dots: THREE.Mesh[] }>();
  private resizeObserver: ResizeObserver;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private time = 0;
  private running = false;
  private visible = false;
  private disposed = false;
  private request = 0;
  private previousTick: number | null = null;
  private lastPublish = -Infinity;
  private texture: SceneSnapshot['texture'] = 'loading';
  private selectedId: string | null = null;
  private hoveredId: string | null = null;
  private pointerStart: { x: number; y: number } | null = null;
  private onSnapshot: (snapshot: SceneSnapshot) => void;
  private container: HTMLElement;
  private handlers: { type: string; listener: EventListener }[] = [];

  constructor(container: HTMLElement, onSnapshot: (snapshot: SceneSnapshot) => void) {
    this.container = container;
    this.onSnapshot = onSnapshot;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'low-power' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0xffffff, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.renderer.domElement.setAttribute('aria-label', 'Interactive 3D Earth and satellite fleet');
    this.renderer.domElement.setAttribute('role', 'img');
    this.renderer.domElement.setAttribute('tabindex', '0');
    this.renderer.domElement.setAttribute('aria-keyshortcuts', 'ArrowUp ArrowDown ArrowLeft ArrowRight');
    this.renderer.domElement.setAttribute('aria-description', 'Drag to rotate the globe. Arrow keys rotate the view.');
    container.appendChild(this.renderer.domElement);
    this.camera.position.copy(initialCamera);
    this.camera.lookAt(0, 0, 0);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = .09;
    this.controls.enableZoom = false;
    this.controls.enablePan = false;
    this.controls.rotateSpeed = .62;
    this.controls.minPolarAngle = .06;
    this.controls.maxPolarAngle = Math.PI - .06;

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.45));
    const sun = new THREE.DirectionalLight(0xfffaf2, 2.7);
    sun.position.set(-3, 4, 6);
    this.scene.add(sun);

    const earthMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1, metalness: 0 });
    this.earth = new THREE.Mesh(new THREE.SphereGeometry(1, 80, 56), earthMaterial);
    this.earth.rotation.y = -Math.PI / 2;
    this.scene.add(this.earth);
    new THREE.TextureLoader().load(`${import.meta.env.BASE_URL}textures/earth-day.jpg`, (texture) => {
      if (this.disposed) { texture.dispose(); return; }
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
      earthMaterial.map = texture;
      earthMaterial.needsUpdate = true;
      this.texture = 'ready';
      this.render(true);
    }, undefined, () => {
      if (this.disposed) return;
      earthMaterial.color.setHex(0xbfcad0);
      this.texture = 'error';
      this.render(true);
    });

    for (const orbit of globeOrbitPaths) {
      const geometry = new THREE.BufferGeometry().setFromPoints(orbit.points.map(vector));
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0xaeb9be, transparent: true, opacity: .54, depthWrite: false }));
      this.scene.add(line);
    }
    for (const station of globeStations) {
      const dot = new THREE.Mesh(new THREE.SphereGeometry(.017, 12, 10), new THREE.MeshBasicMaterial({ color: 0x272727 }));
      dot.position.copy(vector(station).multiplyScalar(1.014));
      this.scene.add(dot);
    }
    for (const satellite of getGlobeFrame(0).satellites) {
      const group = this.makeSatellite(satellite.id);
      this.satellites.set(satellite.id, group);
      this.scene.add(group);
    }
    this.bindInteraction();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  private makeSatellite(id: string) {
    const group = new THREE.Group();
    group.userData.satelliteId = id;
    const body = new THREE.Mesh(new THREE.BoxGeometry(.065, .075, .065), new THREE.MeshStandardMaterial({ color: 0xd8d5cd, roughness: .5, metalness: .4 }));
    group.add(body);
    for (const direction of [-1, 1]) {
      const panel = new THREE.Mesh(new THREE.BoxGeometry(.112, .055, .008), new THREE.MeshStandardMaterial({ color: 0x3d5f78, roughness: .6, metalness: .25 }));
      panel.position.x = direction * .096;
      group.add(panel);
      const lattice = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-.037, -.027, .005), new THREE.Vector3(-.037, .027, .005),
        new THREE.Vector3(0, -.027, .005), new THREE.Vector3(0, .027, .005),
        new THREE.Vector3(.037, -.027, .005), new THREE.Vector3(.037, .027, .005),
        new THREE.Vector3(-.056, 0, .005), new THREE.Vector3(.056, 0, .005),
      ]), new THREE.LineBasicMaterial({ color: 0x9ab3c5, transparent: true, opacity: .7 }));
      panel.add(lattice);
      const arm = new THREE.Mesh(new THREE.BoxGeometry(.045, .008, .008), new THREE.MeshStandardMaterial({ color: 0xb7b7b7, roughness: .6 }));
      arm.position.x = direction * .043;
      group.add(arm);
    }
    const antenna = new THREE.Mesh(new THREE.CylinderGeometry(.003, .003, .047, 6), new THREE.MeshStandardMaterial({ color: 0xbbbbbb, metalness: .3, roughness: .6 }));
    antenna.rotation.x = Math.PI / 2;
    antenna.position.z = .055;
    group.add(antenna);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(.105, .002, 5, 40), new THREE.MeshBasicMaterial({ color: 0x8c1515 }));
    ring.name = 'selection';
    ring.visible = false;
    group.add(ring);
    return group;
  }

  private listen(type: string, listener: EventListener) {
    this.renderer.domElement.addEventListener(type, listener);
    this.handlers.push({ type, listener });
  }

  private bindInteraction() {
    this.listen('pointerdown', ((event: PointerEvent) => { this.pointerStart = { x: event.clientX, y: event.clientY }; }) as EventListener);
    this.listen('pointermove', ((event: PointerEvent) => {
      if (event.buttons) return;
      const hovered = this.pickSatellite(event.clientX, event.clientY);
      if (hovered !== this.hoveredId) { this.hoveredId = hovered; this.render(true); }
      this.renderer.domElement.style.cursor = hovered ? 'pointer' : 'grab';
    }) as EventListener);
    this.listen('pointerleave', (() => { this.hoveredId = null; this.render(true); }) as EventListener);
    this.listen('pointerup', ((event: PointerEvent) => {
      if (this.pointerStart && Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y) < 5) {
        const selected = this.pickSatellite(event.clientX, event.clientY);
        this.selectSatellite(selected === this.selectedId ? null : selected);
      }
      this.pointerStart = null;
    }) as EventListener);
    this.listen('keydown', ((event: KeyboardEvent) => {
      const delta = .12;
      const offset = new THREE.Spherical().setFromVector3(this.camera.position);
      if (event.key === 'ArrowLeft') offset.theta -= delta;
      else if (event.key === 'ArrowRight') offset.theta += delta;
      else if (event.key === 'ArrowUp') offset.phi = Math.max(.08, offset.phi - delta);
      else if (event.key === 'ArrowDown') offset.phi = Math.min(Math.PI - .08, offset.phi + delta);
      else if (event.key === 'Escape') { this.selectSatellite(null); return; }
      else return;
      event.preventDefault();
      this.camera.position.setFromSpherical(offset);
      this.controls.update();
      this.render(true);
    }) as EventListener);
  }

  private pickSatellite(clientX: number, clientY: number): string | null {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((clientX - rect.left) / rect.width * 2 - 1, -(clientY - rect.top) / rect.height * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects([this.earth, ...this.satellites.values()], true)[0];
    if (!hit || hit.object === this.earth) return null;
    let object: THREE.Object3D | null = hit.object;
    while (object) { if (object.userData.satelliteId) return object.userData.satelliteId; object = object.parent; }
    return null;
  }

  private resize() {
    if (this.disposed) return;
    const { width, height } = this.container.getBoundingClientRect();
    this.renderer.setSize(Math.max(1, width), Math.max(1, height), false);
    this.camera.aspect = Math.max(1, width) / Math.max(1, height);
    this.camera.updateProjectionMatrix();
    this.render(true);
  }

  setRunning(running: boolean) {
    this.running = running;
    this.previousTick = null;
    if (!running) this.render(true);
  }

  setVisible(visible: boolean) {
    this.visible = visible;
    this.previousTick = null;
    cancelAnimationFrame(this.request);
    if (visible && !this.disposed) this.request = requestAnimationFrame(this.tick);
  }

  private tick = (now: number) => {
    if (this.disposed || !this.visible) return;
    if (this.previousTick !== null && this.running) this.time = (this.time + Math.min((now - this.previousTick) / 1000, .1)) % GLOBE_LOOP_SECONDS;
    this.previousTick = now;
    const cameraChanged = this.controls.update();
    if (this.running || cameraChanged) this.render(cameraChanged || now - this.lastPublish >= 80);
    this.request = requestAnimationFrame(this.tick);
  };

  nextMoment() { this.running = false; this.time = getNextGlobeContactTime(this.time) % GLOBE_LOOP_SECONDS; this.previousTick = null; this.render(true); }
  reset() { this.running = false; this.time = 0; this.previousTick = null; this.selectedId = null; this.hoveredId = null; this.render(true); }
  selectSatellite(id: string | null) { this.selectedId = id; this.hoveredId = null; this.render(true); }

  focusStation(id: string) {
    const station = globeStations.find((item) => item.id === id);
    this.camera.position.copy(station ? vector(station).normalize().multiplyScalar(cameraDistance) : initialCamera);
    this.controls.target.set(0, 0, 0);
    this.camera.lookAt(0, 0, 0);
    this.controls.update();
    this.render(true);
  }

  private pointVisible(point: THREE.Vector3) {
    const direction = point.clone().sub(this.camera.position);
    const length = direction.length();
    direction.normalize();
    const ray = new THREE.Ray(this.camera.position, direction);
    const hit = ray.intersectSphere(new THREE.Sphere(new THREE.Vector3(), .998), new THREE.Vector3());
    return !hit || hit.distanceTo(this.camera.position) >= length - .015;
  }

  private project(id: string, label: string, point: THREE.Vector3): SceneLabel {
    const projected = point.clone().project(this.camera);
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    return { id, label, x: (projected.x + 1) * width / 2, y: (-projected.y + 1) * height / 2,
      visible: projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < .98 && Math.abs(projected.y) < .98 && this.pointVisible(point) };
  }

  private render(publish: boolean) {
    if (this.disposed) return;
    const frame = getGlobeFrame(this.time);
    const inspected = this.hoveredId ?? this.selectedId;
    for (const satellite of frame.satellites) {
      const group = this.satellites.get(satellite.id)!;
      group.position.copy(vector(satellite));
      const radial = vector(satellite).normalize();
      const tangent = vector(satellite.tangent).normalize();
      const sideways = new THREE.Vector3().crossVectors(radial, tangent).normalize();
      group.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(tangent, sideways, radial));
      group.getObjectByName('selection')!.visible = satellite.id === inspected;
    }
    const active = new Set<string>();
    for (const contact of frame.contacts) {
      const station = frame.stations.find((item) => item.id === contact.stationId)!;
      const satellite = frame.satellites.find((item) => item.id === contact.satelliteId)!;
      const key = `${station.id}/${satellite.id}`;
      active.add(key);
      let link = this.links.get(key);
      if (!link) {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), new THREE.LineBasicMaterial({ color: colors[contact.type], transparent: true, opacity: .8, depthWrite: false }));
        const dots = [0, 1].map(() => new THREE.Mesh(new THREE.SphereGeometry(.011, 8, 6), new THREE.MeshBasicMaterial({ color: colors[contact.type] })));
        link = { line, dots };
        this.links.set(key, link);
        this.scene.add(line, ...dots);
      }
      link.line.visible = true;
      (link.line.material as THREE.LineBasicMaterial).color.setHex(colors[contact.type]);
      const start = vector(station).multiplyScalar(1.016);
      const end = vector(satellite);
      const vertices = link.line.geometry.getAttribute('position') as THREE.BufferAttribute;
      vertices.setXYZ(0, start.x, start.y, start.z);
      vertices.setXYZ(1, end.x, end.y, end.z);
      vertices.needsUpdate = true;
      link.line.geometry.computeBoundingSphere();
      for (let index = 0; index < link.dots.length; index++) {
        const dot = link.dots[index];
        dot.visible = true;
        (dot.material as THREE.MeshBasicMaterial).color.setHex(colors[contact.type]);
        dot.position.lerpVectors(start, end, (this.time * .75 + index * .5) % 1);
      }
    }
    for (const [key, link] of this.links) if (!active.has(key)) { link.line.visible = false; link.dots.forEach((dot) => { dot.visible = false; }); }
    this.renderer.render(this.scene, this.camera);
    if (publish) {
      this.lastPublish = performance.now();
      this.onSnapshot({
        time: this.time, frame, texture: this.texture, camera: this.camera.position.toArray().map((value) => value.toFixed(5)).join(','), inspectedId: inspected, selectedId: this.selectedId,
        stations: frame.stations.map((station) => this.project(station.id, station.label, vector(station).multiplyScalar(1.02))),
        satellites: frame.satellites.map((satellite) => ({ ...this.project(satellite.id, satellite.label, vector(satellite)), orientation: this.satellites.get(satellite.id)!.quaternion.toArray().map((value) => value.toFixed(5)).join(',') })),
      });
    }
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.request);
    this.resizeObserver.disconnect();
    this.controls.dispose();
    for (const handler of this.handlers) this.renderer.domElement.removeEventListener(handler.type, handler.listener);
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    this.scene.traverse((object) => {
      if (object instanceof THREE.DirectionalLight) object.shadow.dispose();
      if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
        geometries.add(object.geometry);
        const source = Array.isArray(object.material) ? object.material : [object.material];
        source.forEach((material) => { materials.add(material); if ('map' in material && material.map instanceof THREE.Texture) textures.add(material.map); });
      }
    });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
