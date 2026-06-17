// =================================================================
// JARVIS AGI HUD — Minimalist Floating Plasma Core (Three.js WebGL)
// =================================================================

// UI STATE REGISTER
let currentState = 'IDLE'; // IDLE, LISTENING, THINKING, SPEAKING, COMPLEX
let currentVolume = 0.0;
let smoothVolume = 0.0;
let thinkingStartTime = null;   // tracks when THINKING state began
let lastResponseMs = null;       // last measured response time in ms

const stateBadge = document.getElementById('main-status');

function setUIState(state) {
    if (!state) return;
    const prev = currentState;
    currentState = state.toUpperCase();
    document.body.className = 'state-' + currentState.toLowerCase();

    // Track response time: start timer when THINKING begins
    if (currentState === 'THINKING') {
        thinkingStartTime = performance.now();
    }
    // Stop timer when SPEAKING begins (first token arrived)
    if (currentState === 'SPEAKING' && thinkingStartTime !== null) {
        lastResponseMs = Math.round(performance.now() - thinkingStartTime);
        thinkingStartTime = null;
        const el = document.getElementById('response-time-val');
        if (el) el.textContent = lastResponseMs + ' ms';
    }

    // Update badge text under the core
    if (stateBadge) {
        stateBadge.textContent = 'CORE ' + currentState;
        if (currentState === 'THINKING') {
            stateBadge.style.color = 'var(--color-cyan)';
        } else if (currentState === 'LISTENING') {
            stateBadge.style.color = 'var(--color-cyan)';
        } else {
            stateBadge.style.color = 'var(--color-emerald)';
        }
    }
}

// ── THREE.JS GLOWING PLASMA ENTITY ENGINE ─────────────────────────
const container = document.querySelector('.canvas-container');
const canvas = document.getElementById('core-3d-canvas');

const scene = new THREE.Scene();

// Camera
const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
camera.position.z = 6;

// Renderer
const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

// GLSL 3D Noise helper functions embedded in shader definition
const noiseShaderCode = `
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}

float snoise(vec3 v){
  const vec2  C = vec2(1.0/6.0, 1.0/3.0) ;
  const vec4  D = vec4(0.0, 0.5, 1.0, 2.0);

  vec3 i  = floor(v + dot(v, C.yyy) );
  vec3 x0 =   v - i + dot(i, C.xxx) ;

  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min( g.xyz, l.zxy );
  vec3 i2 = max( g.xyz, l.zxy );

  vec3 x1 = x0 - i1 + 1.0 * C.xxx;
  vec3 x2 = x0 - i2 + 2.0 * C.xxx;
  vec3 x3 = x0 - D.yyy;

  i = mod(i, 289.0 );
  vec4 p = permute( permute( permute(
             i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
           + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
           + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));

  float n_ = 0.142857142857; // 1.0/7.0
  vec3  ns = n_ * D.wyz - D.xzx;

  vec4 j = p - 49.0 * floor(p * ns.z *ns.z);  //  mod(p,7*7)

  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_ );    // mod(j,N)

  vec4 x = x_ *ns.x + ns.yyyy;
  vec4 y = y_ *ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);

  vec4 b0 = vec4( x.xy, y.xy );
  vec4 b1 = vec4( x.zw, y.zw );

  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));

  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;

  vec3 p0 = vec3(a0.xy,h.x);
  vec3 p1 = vec3(a0.zw,h.y);
  vec3 p2 = vec3(a1.xy,h.z);
  vec3 p3 = vec3(a1.zw,h.w);

  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;

  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1),
                                dot(p2,x2), dot(p3,x3) ) );
}
`;

// Volumetric Custom ShaderMaterial for the bubbling plasma sphere
const plasmaMaterial = new THREE.ShaderMaterial({
    uniforms: {
        uTime: { value: 0.0 },
        uStateSpeed: { value: 1.0 },
        uPulse: { value: 0.0 },
        uColorCyan: { value: new THREE.Color(0x00f0ff) },
        uColorEmerald: { value: new THREE.Color(0x00ffaa) }
    },
    vertexShader: `
        uniform float uTime;
        uniform float uStateSpeed;
        uniform float uPulse;
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying vec3 vViewDirection;
        
        ${noiseShaderCode}
        
        void main() {
            vNormal = normalize(normalMatrix * normal);
            
            // Subtly bubble the surface of the sphere organically based on Simplex Noise
            float noise = snoise(position * 2.2 + uTime * uStateSpeed * 0.45) * (0.08 + uPulse * 0.12);
            vec3 displacedPosition = position + normal * noise;
            
            vec4 mvPosition = modelViewMatrix * vec4(displacedPosition, 1.0);
            vPosition = displacedPosition;
            vViewDirection = normalize(-mvPosition.xyz);
            
            gl_Position = projectionMatrix * mvPosition;
        }
    `,
    fragmentShader: `
        uniform float uTime;
        uniform float uStateSpeed;
        uniform float uPulse;
        uniform vec3 uColorCyan;
        uniform vec3 uColorEmerald;
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying vec3 vViewDirection;
        
        ${noiseShaderCode}
        
        void main() {
            // Faint, smooth fluid energy currents flowing inside the glass shell
            float n1 = snoise(vPosition * 1.5 + vec3(0.0, uTime * uStateSpeed * 0.15, 0.0));
            float n2 = snoise(vPosition * 3.0 - vec3(uTime * uStateSpeed * 0.2, 0.0, uTime * 0.1));
            
            float mixFactor = smoothstep(-0.4, 0.4, n1 + n2 * 0.5);
            vec3 glassColor = mix(uColorEmerald, uColorCyan, mixFactor);
            
            float dotProduct = dot(vNormal, vViewDirection);
            
            // Glass Fresnel: extremely soft, shiny reflections at grazing angles (forms a highly transparent glass shell boundary)
            float glassFresnel = pow(1.0 - max(0.0, dotProduct), 2.8) * 0.65;
            
            // Minimal center opacity/reflection (fully transparent center so core remains perfectly visible)
            float centerReflect = pow(dotProduct, 6.0) * 0.015;
            
            // Combine alpha transparency: highly clear center, glossy bright rim boundary
            float finalAlpha = glassFresnel + centerReflect;
            
            // Add a specular bright white highlight reflection layer on the glass surface
            vec3 finalColor = glassColor * (0.3 + glassFresnel * 1.3) + vec3(1.0) * glassFresnel * 0.45;
            
            // Super transparent (saydam) glass multiplier
            gl_FragColor = vec4(finalColor, finalAlpha * 0.24);
        }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false
});

// Create the main energy plasma core sphere (occupies ~40% of standard views)
const plasmaGeometry = new THREE.SphereGeometry(1.0, 64, 64);
const plasmaCoreMesh = new THREE.Mesh(plasmaGeometry, plasmaMaterial);
// scene.add(plasmaCoreMesh); // Commented out outer large sphere as requested!

// Volumetric Custom ShaderMaterial for the bubbling inner core nucleus (bubbles organically just like the outer orb!)
// Volumetric Custom ShaderMaterial for the bubbling inner core nucleus (bubbles organically just like the outer orb!)
const nucleusMaterial = new THREE.ShaderMaterial({
    uniforms: {
        uTime: { value: 0.0 },
        uStateSpeed: { value: 1.0 },
        uPulse: { value: 0.0 },
        uColor: { value: new THREE.Color(0xffffff) }
    },
    vertexShader: `
        uniform float uTime;
        uniform float uStateSpeed;
        uniform float uPulse;
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying vec3 vViewDirection;
        
        ${noiseShaderCode}
        
        void main() {
            vNormal = normalize(normalMatrix * normal);
            
            // Apply Simplex Noise bubbling directly to the nucleus!
            // Displaces vertices outwards organically based on clock and volume pulse
            float noise = snoise(position * 3.2 + uTime * uStateSpeed * 0.5) * (0.05 + uPulse * 0.08);
            vec3 displacedPosition = position + normal * noise;
            
            vec4 mvPosition = modelViewMatrix * vec4(displacedPosition, 1.0);
            vPosition = displacedPosition;
            vViewDirection = normalize(-mvPosition.xyz);
            
            gl_Position = projectionMatrix * mvPosition;
        }
    `,
    fragmentShader: `
        uniform float uPulse;
        uniform vec3 uColor;
        varying vec3 vNormal;
        varying vec3 vViewDirection;
        
        void main() {
            float dotProduct = dot(vNormal, vViewDirection);
            
            // 1. Tiny dense white core in the absolute center
            float coreMask = pow(max(0.0, dotProduct), 16.0);
            
            // 2. Glass Fresnel: sharp glossy rim reflection at the outer edge of the nucleus bubble
            float glassFresnel = pow(1.0 - max(0.0, dotProduct), 3.0) * 0.55;
            
            // 3. Faint specular reflection in the center
            float specular = pow(max(0.0, dotProduct), 4.0) * 0.2;
            
            // Base glass marble colors (elegant white glass core)
            vec3 glassColor = vec3(1.0, 1.0, 1.0); // Transparent white glass body
            vec3 coreColor = vec3(1.0, 1.0, 1.0); // Pure white core
            vec3 glowColor = vec3(1.0, 1.0, 1.0); // Bright white highlights
            
            // Mix glass body and white core
            vec3 finalColor = mix(glassColor, coreColor, coreMask);
            
            // Add glowing rim highlights and specular
            finalColor += glowColor * (glassFresnel * 0.8 + specular * 0.4);
            
            // Transparency: white core is fully opaque, glass body is highly transparent, glass rim is glossy
            float finalAlpha = coreMask * 0.95 + glassFresnel * 0.45 + 0.05;
            
            gl_FragColor = vec4(finalColor, finalAlpha);
        }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false
});

// Create the inner core nucleus geometry (radius 0.38: holds a beautiful transparent glass bubble with a glowing white core inside)
const nucleusGeometry = new THREE.SphereGeometry(0.38, 32, 32);
const nucleusMesh = new THREE.Mesh(nucleusGeometry, nucleusMaterial);
scene.add(nucleusMesh);

// Helper function to programmatically generate a beautiful circular glowing soft dot texture
function createGlowDotTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 16;
    canvas.height = 16;
    const ctx = canvas.getContext('2d');
    
    const gradient = ctx.createRadialGradient(8, 8, 0, 8, 8, 8);
    gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
    gradient.addColorStop(0.3, 'rgba(255, 255, 255, 0.8)');
    gradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.25)');
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
    
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 16, 16);
    
    return new THREE.CanvasTexture(canvas);
}

// ── SUBTLE HOLOGRAPHIC DUST PARTICLES & faint trails ────────────────
const particleCount = 1000; 
const particleGeo = new THREE.BufferGeometry();
const positions = new Float32Array(particleCount * 3);
const colors = new Float32Array(particleCount * 3);
const particleData = [];
const colorCyan = new THREE.Color(0xffffff); // Pure white particles
const colorEmerald = new THREE.Color(0xffffff); // Pure white particles
const colorOrange = new THREE.Color(0xffffff); // Pure white particles

for (let i = 0; i < particleCount; i++) {
    // Generate mathematically uniform distribution on a 3D sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos((Math.random() - 0.5) * 1.96); // slightly away from absolute poles for premium look
    
    const dx = Math.sin(phi) * Math.cos(theta);
    const dy = Math.cos(phi);
    const dz = Math.sin(phi) * Math.sin(theta);
    
    // Position on a sphere of radius 1.0 + hoverOffset + scatter
    const hoverOffset = 0.02 + Math.random() * 0.06;
    const scatterOffset = (Math.random() - 0.5) * 0.38;
    const initialSphereRadius = 1.0 + hoverOffset + scatterOffset;
    
    const x = dx * initialSphereRadius;
    const y = dy * initialSphereRadius;
    const z = dz * initialSphereRadius;
    
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    
    // Mix cyan, emerald, and gorgeous orange particles
    const rand = Math.random();
    const isOrange = rand <= 0.3; // Identifies orange particles (rand <= 0.3 matches colorOrange below)
    const isEmerald = rand > 0.3 && rand <= 0.65; // Identifies green particles
    const isCyan = rand > 0.65; // Identifies cyan particles
    
    // Assign a prominence factor to approx 18% of the particles to form the outer looping flares (prominences)
    const prominenceFactor = Math.random() > 0.82 ? (0.4 + Math.random() * 0.6) : 0.0;
    
    particleData.push({
        dx: dx,
        dy: dy,
        dz: dz,
        orbitAngle: Math.random() * Math.PI * 2,
        speed: 0.0022 + Math.random() * 0.0038, // balanced base speed for premium visible movement
        isOrange: isOrange,
        isEmerald: isEmerald,
        isCyan: isCyan,
        hoverOffset: hoverOffset,
        prominenceFactor: prominenceFactor,
        scatterOffset: scatterOffset
    });
    
    const blendColor = rand > 0.65 ? colorCyan : (rand > 0.3 ? colorEmerald : colorOrange);
    
    colors[i * 3] = blendColor.r;
    colors[i * 3 + 1] = blendColor.g;
    colors[i * 3 + 2] = blendColor.b;
}

particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

const particleMat = new THREE.PointsMaterial({
    size: 0.095, // Slightly larger size for circular soft glow falloff
    map: createGlowDotTexture(),
    vertexColors: true,
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
    depthWrite: false
});

const particleSystem = new THREE.Points(particleGeo, particleMat);
scene.add(particleSystem);

// ── CONSTELLATION LINE CONNECTIONS (NEURAL NET WEB EFFECT) ──────────
const connections = [];
// Calculate connections between nearby particles at startup to form a beautiful geodesic network
for (let i = 0; i < particleCount; i++) {
    const list = [];
    const xi = positions[i * 3];
    const yi = positions[i * 3 + 1];
    const zi = positions[i * 3 + 2];
    
    for (let j = i + 1; j < particleCount; j++) {
        const xj = positions[j * 3];
        const yj = positions[j * 3 + 1];
        const zj = positions[j * 3 + 2];
        const dx = xi - xj;
        const dy = yi - yj;
        const dz = zi - zj;
        const distSq = dx * dx + dy * dy + dz * dz;
        // Connect points that are extremely close at startup (distance < ~0.18 units)
        if (distSq < 0.035) {
            list.push({ index: j, distSq: distSq });
        }
    }
    list.sort((a, b) => a.distSq - b.distSq);
    // Connect each particle to at most 1 closest neighbor to keep the constellation extremely sparse and luxury-clean
    const maxConns = Math.min(list.length, 1);
    for (let c = 0; c < maxConns; c++) {
        connections.push({ from: i, to: list[c].index });
    }
}

const linePositions = new Float32Array(connections.length * 2 * 3);
const lineColors = new Float32Array(connections.length * 2 * 3);

const lineGeo = new THREE.BufferGeometry();
lineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
lineGeo.setAttribute('color', new THREE.BufferAttribute(lineColors, 3));

const lineMat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.12, // ultra subtle premium thin thread glow
    blending: THREE.AdditiveBlending,
    depthWrite: false
});

const lineSystem = new THREE.LineSegments(lineGeo, lineMat);
scene.add(lineSystem);

// Resize handler
window.addEventListener('resize', () => {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});

// ANIMATION LOOP (60 FPS)
let clock = 0;
let thinkingInterpolation = 0.0;
let speakingInterpolation = 0.0;
let voiceGrowInterp = 0.0; // Ses bazlı büyüme: sesle anında büyür, sessizlikte hemen küçülür

const defaultCyan = new THREE.Color(0x00f0ff);
const defaultEmerald = new THREE.Color(0x00ffaa);

const thinkingOrange = new THREE.Color(0xff4400); // Deep glowing orange/red-orange
const thinkingYellow = new THREE.Color(0xffaa00); // Golden bright yellow

const speakingGreen = new THREE.Color(0x00ff22); // Vibrant glowing speaking green
const speakingLime = new THREE.Color(0x77ff00); // Lime speaking color

function animate() {
    requestAnimationFrame(animate);
    
    // Smooth volume inputs
    smoothVolume += (currentVolume - smoothVolume) * 0.1;
    
    // Konuşma algısı: state VEYA volume — backend volume göndermese de state=SPEAKING yeterli
    // Hem normal konuşmada hem internet araması sonrasında AYNI davranış
    let isSpeakingActive = (currentState === 'SPEAKING' || smoothVolume > 0.015 || currentVolume > 0.015);
    
    // Smoothly accelerate core rotation and particle orbits when speaking (refined majestic sci-fi swirl!)
    let masterSpeed = 0.16 + 0.34 * voiceGrowInterp;      // accelerates from 0.16 to 0.5
    let particleOrbitFactor = 0.16 + 0.54 * voiceGrowInterp; // orbits speed up from 0.16 to 0.7
    
    // Smooth transition tracking for THINKING state
    if (currentState === 'THINKING') {
        thinkingInterpolation += (1.0 - thinkingInterpolation) * 0.08;
    } else {
        // Konuşmaya geçince thinking çok hızlı sıfırlanır
        let fadeSpeed = isSpeakingActive ? 0.25 : 0.08;
        thinkingInterpolation += (0.0 - thinkingInterpolation) * fadeSpeed;
    }
    
    // Smooth transition tracking for SPEAKING state
    if (isSpeakingActive) {
        speakingInterpolation += (1.0 - speakingInterpolation) * 0.12;
    } else {
        speakingInterpolation += (0.0 - speakingInterpolation) * 0.12;
    }
    
    // Volume-reactive büyüme — hem normal hem internet araması sonrası AYNI şekilde
    // isSpeakingActive true iken hızlıca büyür, false iken hızlıca küçülür (anlık zıplama yok)
    let voiceDetected = isSpeakingActive;
    if (voiceDetected) {
        voiceGrowInterp += (1.0 - voiceGrowInterp) * 0.18; // yumuşak büyüme
    } else {
        voiceGrowInterp += (0.0 - voiceGrowInterp) * 0.18; // yumuşak küçülme
    }
    
    clock += 0.002 * masterSpeed;
    
    // Internal light pulsing factor
    let pulse = Math.sin(clock * 4.0) * 0.05;
    if (currentState === 'THINKING') {
        pulse = Math.sin(clock * 15.0) * 0.15;
    } else if (isSpeakingActive) {
        pulse = smoothVolume * 0.45;
    }
    
    // Interpolate outer sphere colors dynamically with absolute state separation
    let finalCyan = new THREE.Color();
    let finalEmerald = new THREE.Color();
    
    if (currentState === 'THINKING') {
        finalCyan.lerpColors(defaultCyan, thinkingOrange, thinkingInterpolation);
        finalEmerald.lerpColors(defaultEmerald, thinkingYellow, thinkingInterpolation);
    } else if (currentState === 'SPEAKING') {
        finalCyan.lerpColors(defaultCyan, speakingGreen, speakingInterpolation);
        finalEmerald.lerpColors(defaultEmerald, speakingLime, speakingInterpolation);
    } else {
        // Smoothly fade back to default Cyan/Emerald from whichever state is currently deactivating
        if (thinkingInterpolation > 0.0) {
            finalCyan.lerpColors(defaultCyan, thinkingOrange, thinkingInterpolation);
            finalEmerald.lerpColors(defaultEmerald, thinkingYellow, thinkingInterpolation);
        } else if (speakingInterpolation > 0.0) {
            finalCyan.lerpColors(defaultCyan, speakingGreen, speakingInterpolation);
            finalEmerald.lerpColors(defaultEmerald, speakingLime, speakingInterpolation);
        } else {
            finalCyan.copy(defaultCyan);
            finalEmerald.copy(defaultEmerald);
        }
    }
    
    plasmaMaterial.uniforms.uColorCyan.value.copy(finalCyan);
    plasmaMaterial.uniforms.uColorEmerald.value.copy(finalEmerald);
    
    // Update Shader Uniforms
    plasmaMaterial.uniforms.uTime.value = clock;
    plasmaMaterial.uniforms.uStateSpeed.value = masterSpeed;
    plasmaMaterial.uniforms.uPulse.value = pulse;
    
    // Undulate core size (Shrink outer sphere scale down during thinking AND speaking!)
    // Core scaling now reacts to voice (grows while speaking) and shrinks only during THINKING
    let baseScale = 1.0 - 0.45 * thinkingInterpolation + 0.35 * voiceGrowInterp;
    plasmaCoreMesh.scale.setScalar(baseScale + pulse * 0.2);
    plasmaCoreMesh.rotation.y += 0.002 * masterSpeed;
    plasmaCoreMesh.rotation.z += 0.0006 * masterSpeed;
    
    // Animate central core nucleus in sync (make it rotate and bubble organically!)
    if (nucleusMesh) {
        nucleusMaterial.uniforms.uTime.value = clock;
        nucleusMaterial.uniforms.uStateSpeed.value = masterSpeed;
        nucleusMaterial.uniforms.uPulse.value = pulse;
        
        // Konuşunca nucleus de büyür — voiceGrowInterp ile (asıl görünen bu!)
        let nucleusGrow = 1.0 + voiceGrowInterp * 0.35 + pulse * 0.15;
        nucleusMesh.scale.setScalar(nucleusGrow);
        nucleusMesh.rotation.y -= 0.008 * masterSpeed;
        nucleusMesh.rotation.x += 0.004 * masterSpeed;
    }

    
    // Animate subtle holographic dust
    const positionsAttr = particleSystem.geometry.attributes.position;
    for (let i = 0; i < particleCount; i++) {
        const data = particleData[i];
        
        // Update orbit angle
        data.orbitAngle += data.speed * particleOrbitFactor;
        
        // Mathematically correct Y-axis rotation in 3D
        const rx = data.dx * Math.cos(data.orbitAngle) - data.dz * Math.sin(data.orbitAngle);
        const ry = data.dy;
        const rz = data.dx * Math.sin(data.orbitAngle) + data.dz * Math.cos(data.orbitAngle);
        
        let prominenceOffset = 0.0;
        if (data.prominenceFactor > 0.0) {
            let loopWave = Math.sin(data.orbitAngle * 3.0 + clock * 2.0) * Math.cos(data.orbitAngle * 1.5);
            prominenceOffset = Math.max(0.0, loopWave) * 0.52 * data.prominenceFactor;
        }
        
        let organicDeform = Math.sin(data.orbitAngle * 3.0) * Math.cos(ry * 2.0) * 0.09 + 
                            Math.cos(data.orbitAngle * 2.0 + clock * 0.45) * Math.sin(ry * 3.2) * 0.08 +
                            Math.sin(data.orbitAngle * 1.0 - clock * 0.2) * 0.04;
        
        // Ses varken büyür, sessizlikte küçülür (cümle araları dahil)
        let growFactor = 0.35 * voiceGrowInterp; // premium dengeli büyüme
        
        // Spherically symmetric radius in 3D
        let R = 1.0 + data.hoverOffset + data.scatterOffset + organicDeform + prominenceOffset + growFactor;
        
        // True 3D uniform spherical projection (no flattening, perfect distribution!)
        const x = rx * R;
        const y = ry * R;
        const z = rz * R;
        
        positionsAttr.setXYZ(i, x, y, z);
    }
    positionsAttr.needsUpdate = true;
    
    // Update constellation line geometries in real time to match particle movements
    if (typeof lineSystem !== 'undefined' && lineSystem) {
        const linePosAttr = lineSystem.geometry.attributes.position;
        const lineColAttr = lineSystem.geometry.attributes.color;
        
        let lineIdx = 0;
        for (let c = 0; c < connections.length; c++) {
            const conn = connections[c];
            
            const x1 = positionsAttr.getX(conn.from);
            const y1 = positionsAttr.getY(conn.from);
            const z1 = positionsAttr.getZ(conn.from);
            
            const x2 = positionsAttr.getX(conn.to);
            const y2 = positionsAttr.getY(conn.to);
            const z2 = positionsAttr.getZ(conn.to);
            
            linePosAttr.setXYZ(lineIdx, x1, y1, z1);
            linePosAttr.setXYZ(lineIdx + 1, x2, y2, z2);
            
            // Determine cyan/emerald colors for lines (staying default cyan/emerald during speaking)
            let lineCyan = defaultCyan;
            let lineEmerald = defaultEmerald;
            
            if (thinkingInterpolation > 0.0) {
                lineCyan = new THREE.Color().lerpColors(defaultCyan, thinkingOrange, thinkingInterpolation);
                lineEmerald = new THREE.Color().lerpColors(defaultEmerald, thinkingYellow, thinkingInterpolation);
            }
            
            // Generate glowing translucent lines lerped dynamically with state colors
            const factor = (y1 + y2 + 2.0) / 4.0;
            const cMix = lineCyan.clone().lerp(lineEmerald, Math.max(0.0, Math.min(1.0, factor)));
            
            lineColAttr.setXYZ(lineIdx, cMix.r, cMix.g, cMix.b);
            lineColAttr.setXYZ(lineIdx + 1, cMix.r, cMix.g, cMix.b);
            
            lineIdx += 2;
        }
        linePosAttr.needsUpdate = true;
        lineColAttr.needsUpdate = true;
    }
    
    renderer.render(scene, camera);
}
animate();

// ── UI INTERACTION & METRICS CONTROLLER ───────────────────────────
const chatLogs = document.getElementById('chat-logs');
const btnMic = document.getElementById('btn-mic');
const btnPower = document.getElementById('btn-power');
const iconMicActive = document.querySelector('.icon-mic-active');
const iconMicMuted = document.querySelector('.icon-mic-muted');

const cpuVal = document.getElementById('cpu-val');
const cpuBar = document.getElementById('cpu-bar');
const ramVal = document.getElementById('ram-val');
const ramBar = document.getElementById('ram-bar');
const vramVal = document.getElementById('vram-val');
const vramBar = document.getElementById('vram-bar');
const vramMbVal = document.getElementById('vram-mb-val');

function addChatEntry(sender, text) {
    if (!chatLogs || !text) return;
    
    const entry = document.createElement('div');
    entry.className = 'chat-entry ' + sender.toLowerCase();
    
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const timestamp = document.createElement('span');
    timestamp.className = 'timestamp';
    timestamp.textContent = '[' + timeStr + '] ' + sender.toUpperCase();
    
    const message = document.createElement('span');
    message.className = 'message';
    message.textContent = text;
    
    entry.appendChild(timestamp);
    entry.appendChild(message);
    chatLogs.appendChild(entry);
    
    // Auto-scroll
    chatLogs.scrollTop = chatLogs.scrollHeight;
}

// ── STREAMING TYPEWRITER SUPPORT ─────────────────────────────────
let _streamBubble = null; // current live streaming bubble element
let _streamText = '';     // accumulated text in the current stream

function startStreamBubble() {
    // Close any previous streaming bubble
    if (_streamBubble) {
        _streamBubble.classList.remove('streaming');
        _streamBubble = null;
    }
    _streamText = '';
    
    const entry = document.createElement('div');
    entry.className = 'chat-entry jarvis streaming';
    
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const timestamp = document.createElement('span');
    timestamp.className = 'timestamp';
    timestamp.textContent = '[' + timeStr + '] JARVIS';
    
    const message = document.createElement('span');
    message.className = 'message';
    message.textContent = '';
    
    entry.appendChild(timestamp);
    entry.appendChild(message);
    chatLogs.appendChild(entry);
    chatLogs.scrollTop = chatLogs.scrollHeight;
    
    _streamBubble = entry;
}

function appendStreamToken(token) {
    if (!_streamBubble) return;
    _streamText += token;
    const msgEl = _streamBubble.querySelector('.message');
    if (msgEl) {
        msgEl.textContent = _streamText;
        chatLogs.scrollTop = chatLogs.scrollHeight;
    }
}

function updateMicButton(status) {
    if (!btnMic) return;
    if (status === 'muted') {
        btnMic.classList.add('muted');
        if (iconMicActive) iconMicActive.style.display = 'none';
        if (iconMicMuted) iconMicMuted.style.display = 'block';
    } else {
        btnMic.classList.remove('muted');
        if (iconMicActive) iconMicActive.style.display = 'block';
        if (iconMicMuted) iconMicMuted.style.display = 'none';
    }
}

function updateSysStats(stats) {
    if (cpuVal && cpuBar && stats.cpu !== undefined) {
        cpuVal.textContent = Math.round(stats.cpu) + '%';
        cpuBar.style.width = stats.cpu + '%';
    }
    if (ramVal && ramBar && stats.ram !== undefined) {
        ramVal.textContent = Math.round(stats.ram) + '%';
        ramBar.style.width = stats.ram + '%';
    }
    if (vramVal && vramBar && stats.vram !== undefined) {
        vramVal.textContent = Math.round(stats.vram) + '%';
        vramBar.style.width = stats.vram + '%';
    }
    if (vramMbVal && stats.vram_mb !== undefined) {
        vramMbVal.textContent = stats.vram_mb + ' MB / 12288 MB';
    }
}

// ── PLANS WIDGET RENDERER ─────────────────────────────────────────
function renderPlans(plans) {
    const container = document.getElementById('plans-list');
    if (!container) return;
    if (!plans || plans.length === 0) {
        container.innerHTML = '<div class="widget-empty">Aktif plan yok</div>';
        return;
    }
    // Show max 4 upcoming active plans
    const active = plans.filter(p => p.status === 'active').slice(0, 4);
    if (active.length === 0) {
        container.innerHTML = '<div class="widget-empty">Aktif plan yok</div>';
        return;
    }
    container.innerHTML = active.map(p => {
        const dateStr = p.date || '';
        const timeStr = p.time || '';
        const subject = p.subject || '';
        return `<div class="plan-item">
            <span class="plan-subject">${subject}</span>
            <span class="plan-datetime">${dateStr} ${timeStr}</span>
        </div>`;
    }).join('');
}

// ── MODEL INFO STATIC FILL ────────────────────────────────────────
function initModelInfo() {
    const modelEl = document.getElementById('model-name-val');
    const embedEl = document.getElementById('embed-name-val');
    if (modelEl) modelEl.textContent = 'qwen3:14b';
    if (embedEl) embedEl.textContent = 'nomic-embed-text';
}
initModelInfo();

// ── LOAD PLANS FROM memory.json VIA FETCH ─────────────────────────
function refreshPlans() {
    // Fetch memory.json directly from filesystem (works in pywebview / local file context)
    fetch('../memory.json?v=' + Date.now())
        .then(r => r.json())
        .then(mem => renderPlans(mem.reminders || []))
        .catch(() => {});
}
refreshPlans();
setInterval(refreshPlans, 10000); // refresh every 10 seconds

// ── WEBSOCKET BROKER SYNC ─────────────────────────────────────────
function connectWS() {
    const ws = new WebSocket('ws://127.0.0.1:7474');
    
    ws.onopen = () => {
        console.log('[JARVIS HUD] WebSocket Connected.');
    };
    
    ws.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'state') setUIState(data.value);
            if (data.type === 'volume') currentVolume = parseFloat(data.value);
            if (data.type === 'transcript') addChatEntry('user', data.value);
            
            // Streaming typewriter: open a new bubble
            if (data.type === 'stream_start') {
                startStreamBubble();
            }
            // Streaming typewriter: append token to current bubble
            if (data.type === 'stream_token') {
                appendStreamToken(data.value);
            }
            // Final response: only add a new entry if we were NOT streaming
            // (if _streamBubble exists, streaming already displayed the text)
            if (data.type === 'response') {
                if (!_streamBubble) {
                    // Non-streaming path (interceptors, greetings, etc.)
                    addChatEntry('jarvis', data.value);
                } else {
                    // Streaming finished — finalize the bubble
                    if (_streamBubble) {
                        _streamBubble.classList.remove('streaming');
                        _streamBubble = null;
                    }
                }
                // Refresh plans after every Jarvis reply (plans may have changed)
                setTimeout(refreshPlans, 500);
            }
            if (data.type === 'mic_status') updateMicButton(data.value);
            if (data.type === 'sys_stats') updateSysStats(data.value);
        } catch (err) {}
    };
    
    ws.onclose = () => {
        setTimeout(connectWS, 2500);
    };
    ws.onerror = () => ws.close();
    
    // Bind click events on buttons
    if (btnMic) {
        btnMic.onclick = () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'control', action: 'toggle_mute' }));
            }
        };
    }
    
    if (btnPower) {
        btnPower.onclick = () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'control', action: 'shutdown' }));
            }
        };
    }
}
connectWS();

window.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    if (key === 't') {
        setUIState('THINKING');
    } else if (key === 'i') {
        setUIState('IDLE');
    } else if (key === 'l') {
        setUIState('LISTENING');
    } else if (key === 's') {
        setUIState('SPEAKING');
    }
});
