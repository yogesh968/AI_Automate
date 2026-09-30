import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

// Look + motion targets per orb state. Values are eased toward every frame.
const STATES = {
  idle:      { amp: 0.07, freq: 1.3, speed: 0.35, ring: 0.35, intensity: 0.95, scale: 0.92, a: '#0a8cff', b: '#7df9ff' },
  listening: { amp: 0.12, freq: 1.7, speed: 0.9,  ring: 0.9,  intensity: 1.25, scale: 1.0,  a: '#00c8ff', b: '#e8fdff' },
  thinking:  { amp: 0.16, freq: 2.2, speed: 1.7,  ring: 3.6,  intensity: 1.15, scale: 0.96, a: '#2f6bff', b: '#b69cff' },
  speaking:  { amp: 0.10, freq: 1.5, speed: 1.0,  ring: 1.2,  intensity: 1.3,  scale: 1.0,  a: '#12d6f5', b: '#f0fbff' },
  sleeping:  { amp: 0.03, freq: 1.0, speed: 0.15, ring: 0.1,  intensity: 0.35, scale: 0.85, a: '#123a66', b: '#3f6f99' },
  error:     { amp: 0.2,  freq: 2.4, speed: 1.2,  ring: 0.6,  intensity: 1.1,  scale: 0.94, a: '#ff2d3d', b: '#ffb199' },
  offline:   { amp: 0.03, freq: 1.0, speed: 0.2,  ring: 0.15, intensity: 0.4,  scale: 0.86, a: '#3a4757', b: '#7a8898' },
};

// Ashima 3D simplex noise.
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
`;

const SPHERE_VERT = /* glsl */ `
uniform float uTime;
uniform float uAmp;
uniform float uFreq;
varying vec3 vNormal;
varying vec3 vView;
varying float vNoise;
${NOISE}
void main(){
  float n = snoise(normal * uFreq + vec3(uTime * 0.6, uTime * 0.4, uTime * 0.5));
  float n2 = snoise(normal * uFreq * 2.3 - vec3(uTime * 0.9));
  float d = n * 0.75 + n2 * 0.25;
  vNoise = d;
  vec3 pos = position + normal * d * uAmp;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;

const SPHERE_FRAG = /* glsl */ `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uIntensity;
uniform float uTime;
varying vec3 vNormal;
varying vec3 vView;
varying float vNoise;
void main(){
  float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.2);
  vec3 base = mix(uColorA * 0.55, uColorB, smoothstep(-0.4, 0.8, vNoise));
  // faint latitude scan lines for the HUD feel
  float scan = 0.06 * sin(vNormal.y * 60.0 + uTime * 3.0);
  vec3 col = base * (0.45 + 0.55 * (1.0 - fres)) + uColorB * fres * 1.6 + scan;
  float alpha = clamp(0.78 + fres * 0.4, 0.0, 1.0);
  gl_FragColor = vec4(col * uIntensity, alpha);
}
`;

const GLOW_VERT = /* glsl */ `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

const GLOW_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uIntensity;
varying vec2 vUv;
void main(){
  float d = distance(vUv, vec2(0.5)) * 2.0;
  float g = pow(max(1.0 - d, 0.0), 2.4);
  gl_FragColor = vec4(uColor * g * uIntensity, g * uIntensity);
}
`;

function makeArc(inner, outer, start, length, opacity) {
  const geo = new THREE.RingGeometry(inner, outer, 96, 1, start, length);
  const mat = new THREE.MeshBasicMaterial({
    color: 0x7df9ff,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Mesh(geo, mat);
}

export default function Orb({ state = 'idle', getLevel }) {
  const mountRef = useRef(null);
  const stateRef = useRef(state);
  const levelRef = useRef(getLevel);
  stateRef.current = state;
  levelRef.current = getLevel;

  useEffect(() => {
    const mount = mountRef.current;
    const size = () => ({ w: mount.clientWidth || 140, h: mount.clientHeight || 140 });

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: false });
    } catch (err) {
      console.warn('[orb] WebGL unavailable, using CSS fallback', err);
      mount.classList.add('orb-fallback');
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    const { w, h } = size();
    renderer.setSize(w, h);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
    camera.position.set(0, 0, 6.2);

    const group = new THREE.Group();
    scene.add(group);

    // Outer glow
    const glowMat = new THREE.ShaderMaterial({
      vertexShader: GLOW_VERT,
      fragmentShader: GLOW_FRAG,
      uniforms: { uColor: { value: new THREE.Color('#00c8ff') }, uIntensity: { value: 0.8 } },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(3.9, 3.9), glowMat);
    glow.position.z = -0.8;
    scene.add(glow);

    // Core sphere
    const sphereMat = new THREE.ShaderMaterial({
      vertexShader: SPHERE_VERT,
      fragmentShader: SPHERE_FRAG,
      uniforms: {
        uTime: { value: 0 },
        uAmp: { value: 0.07 },
        uFreq: { value: 1.3 },
        uColorA: { value: new THREE.Color('#0a8cff') },
        uColorB: { value: new THREE.Color('#7df9ff') },
        uIntensity: { value: 1 },
      },
      transparent: true,
    });
    const sphere = new THREE.Mesh(new THREE.IcosahedronGeometry(0.95, 48), sphereMat);
    group.add(sphere);

    // HUD arcs
    const rings = [
      { mesh: makeArc(1.22, 1.25, 0, Math.PI * 1.55, 0.75), dir: 1, mult: 1 },
      { mesh: makeArc(1.34, 1.36, Math.PI * 0.3, Math.PI * 0.6, 0.55), dir: -1, mult: 1.6 },
      { mesh: makeArc(1.34, 1.36, Math.PI * 1.3, Math.PI * 0.45, 0.55), dir: -1, mult: 1.6 },
      { mesh: makeArc(1.48, 1.5, 0, Math.PI * 0.9, 0.35), dir: 1, mult: 0.7 },
      { mesh: makeArc(1.48, 1.5, Math.PI, Math.PI * 0.55, 0.35), dir: 1, mult: 0.7 },
    ];
    const ringGroup = new THREE.Group();
    rings.forEach((r) => ringGroup.add(r.mesh));
    ringGroup.rotation.x = 0.35;
    scene.add(ringGroup);

    // Tick marks on the outer ring
    const ticks = new THREE.Group();
    for (let i = 0; i < 48; i++) {
      const t = makeArc(1.58, i % 4 === 0 ? 1.66 : 1.62, (i / 48) * Math.PI * 2, 0.018, 0.4);
      ticks.add(t);
    }
    scene.add(ticks);

    // Orbiting particles
    const COUNT = 220;
    const positions = new Float32Array(COUNT * 3);
    const seeds = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT; i++) {
      seeds[i * 3] = Math.random() * Math.PI * 2; // angle
      seeds[i * 3 + 1] = 1.1 + Math.random() * 0.55; // radius
      seeds[i * 3 + 2] = (Math.random() - 0.5) * 0.5; // height
    }
    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const pMat = new THREE.PointsMaterial({
      color: 0x9ff7ff,
      size: 0.035,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const particles = new THREE.Points(pGeo, pMat);
    particles.rotation.x = 0.35;
    scene.add(particles);

    // Eased values
    const cur = {
      amp: 0.07, freq: 1.3, speed: 0.35, ring: 0.35, intensity: 0.95, scale: 0.92,
      a: new THREE.Color('#0a8cff'), b: new THREE.Color('#7df9ff'), level: 0,
    };
    const tmpA = new THREE.Color();
    const tmpB = new THREE.Color();

    let raf = 0;
    let last = performance.now();
    let t = 0;
    let ringAngle = 0;
    let visible = true;

    const onVisibility = () => {
      visible = document.visibilityState === 'visible';
    };
    document.addEventListener('visibilitychange', onVisibility);

    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const s = STATES[stateRef.current] || STATES.idle;
      const k = 1 - Math.exp(-dt * 6);

      const rawLevel =
        stateRef.current === 'listening' || stateRef.current === 'speaking'
          ? Math.max(0, Math.min(1, levelRef.current?.() || 0))
          : 0;
      cur.level += (rawLevel - cur.level) * (1 - Math.exp(-dt * 18));
      const L = cur.level;

      cur.amp += (s.amp + L * 0.45 - cur.amp) * k;
      cur.freq += (s.freq - cur.freq) * k;
      cur.speed += (s.speed + L * 0.8 - cur.speed) * k;
      cur.ring += (s.ring + L * 1.5 - cur.ring) * k;
      cur.intensity += (s.intensity + L * 0.5 - cur.intensity) * k;
      const breathe = stateRef.current === 'idle' || stateRef.current === 'sleeping'
        ? Math.sin(now / 1000 * 1.4) * 0.025
        : 0;
      cur.scale += (s.scale + L * 0.16 + breathe - cur.scale) * k;
      cur.a.lerp(tmpA.set(s.a), k);
      cur.b.lerp(tmpB.set(s.b), k);

      t += dt * cur.speed;
      ringAngle += dt * cur.ring;

      sphereMat.uniforms.uTime.value = t;
      sphereMat.uniforms.uAmp.value = cur.amp;
      sphereMat.uniforms.uFreq.value = cur.freq;
      sphereMat.uniforms.uColorA.value.copy(cur.a);
      sphereMat.uniforms.uColorB.value.copy(cur.b);
      sphereMat.uniforms.uIntensity.value = cur.intensity;
      group.scale.setScalar(cur.scale);
      sphere.rotation.y += dt * 0.25;

      glowMat.uniforms.uColor.value.copy(cur.a).lerp(cur.b, 0.35);
      glowMat.uniforms.uIntensity.value = 0.55 + cur.intensity * 0.35 + L * 0.6;

      rings.forEach((r, i) => {
        r.mesh.rotation.z = ringAngle * r.dir * r.mult + i;
        r.mesh.material.color.copy(cur.b);
      });
      ringGroup.scale.setScalar(0.96 + cur.scale * 0.04 + L * 0.06);
      ticks.rotation.z = -ringAngle * 0.15;
      ticks.children.forEach((m) => m.material.color.copy(cur.a).lerp(cur.b, 0.5));

      for (let i = 0; i < COUNT; i++) {
        const ang = seeds[i * 3] + t * (0.4 + (i % 7) * 0.05);
        const rad = seeds[i * 3 + 1] + Math.sin(t * 2 + i) * 0.03 + L * 0.25;
        positions[i * 3] = Math.cos(ang) * rad;
        positions[i * 3 + 1] = seeds[i * 3 + 2] + Math.sin(ang * 2 + t) * 0.05;
        positions[i * 3 + 2] = Math.sin(ang) * rad;
      }
      pGeo.attributes.position.needsUpdate = true;
      pMat.color.copy(cur.b);
      pMat.opacity = 0.35 + cur.intensity * 0.4;

      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);

    const ro = new ResizeObserver(() => {
      const { w: nw, h: nh } = size();
      renderer.setSize(nw, nh);
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
    });
    ro.observe(mount);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      scene.traverse((obj) => {
        obj.geometry?.dispose?.();
        obj.material?.dispose?.();
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div className={`orb orb-${state}`} ref={mountRef} />;
}
