"use client";
import {useEffect,useRef} from 'react';
import * as THREE from 'three';
import {sampleConstellation} from './constellations.mjs';
export default function Space({playing}:{playing:boolean}){
 const host=useRef<HTMLDivElement>(null),active=useRef(playing),needsFrame=useRef(true);
 useEffect(()=>{active.current=playing;needsFrame.current=true},[playing]);
 useEffect(()=>{
  if(!host.current)return;const el=host.current;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({alpha:true,antialias:false,powerPreference:'low-power'})}catch{return}
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,1.5));renderer.setClearColor(0x050610,0);el.appendChild(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(48,1,.1,100);camera.position.z=6;
  const positions=new Float32Array(2100*3),colors=new Float32Array(2100*3);let seed=47;const random=()=>{seed=(seed*16807)%2147483647;return(seed-1)/2147483646};
  for(let i=0;i<2100;i++){positions[i*3]=(random()-.5)*35;positions[i*3+1]=(random()-.5)*22;positions[i*3+2]=-random()*15;const c=new THREE.Color().setHSL(.60+random()*.16,.2+random()*.3,.45+random()*.5);colors[i*3]=c.r;colors[i*3+1]=c.g;colors[i*3+2]=c.b;}
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(positions,3));geo.setAttribute('color',new THREE.BufferAttribute(colors,3));
  const material=new THREE.PointsMaterial({size:.026,vertexColors:true,transparent:true,opacity:.95,depthWrite:false,sizeAttenuation:true});const stars=new THREE.Points(geo,material);scene.add(stars);
  const constellation=new THREE.Group();scene.add(constellation);
  const lineGeo=new THREE.BufferGeometry(),linePositions=new Float32Array(200*3);
  lineGeo.setAttribute('position',new THREE.BufferAttribute(linePositions,3));lineGeo.setDrawRange(0,0);
  const lineMaterial=new THREE.LineBasicMaterial({color:0xb78aff,transparent:true,opacity:.6,depthWrite:false});
  const lines=new THREE.LineSegments(lineGeo,lineMaterial);lines.frustumCulled=false;constellation.add(lines);
  const nodeGeo=new THREE.BufferGeometry(),nodePositions=new Float32Array(100*3);
  nodeGeo.setAttribute('position',new THREE.BufferAttribute(nodePositions,3));nodeGeo.setDrawRange(0,0);
  const nodeMaterial=new THREE.PointsMaterial({color:0xe6d7ff,size:.047,transparent:true,opacity:.9,depthWrite:false});
  const nodes=new THREE.Points(nodeGeo,nodeMaterial);nodes.frustumCulled=false;constellation.add(nodes);
  function drawConstellation(time:number){
   const sample=sampleConstellation(time,!active.current&&time===0),{shape,completed,progress,opacity}=sample;
   let count=0;const reached=new Set<number>();
   for(let edge=0;edge<Math.min(shape.edges.length,completed+1);edge++){
    const [from,to]=shape.edges[edge],a=shape.points[from],b=shape.points[to],t=edge<completed?1:progress;
    if(t<=0)continue;reached.add(from);if(t===1)reached.add(to);
    linePositions.set(a,count*3);count++;
    linePositions.set([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t],count*3);count++;
   }
   lineGeo.setDrawRange(0,count);lineGeo.attributes.position.needsUpdate=true;
   let n=0;for(const point of reached)nodePositions.set(shape.points[point],n++*3);
   nodeGeo.setDrawRange(0,n);nodeGeo.attributes.position.needsUpdate=true;
   lineMaterial.opacity=opacity*.62;nodeMaterial.opacity=opacity*.92;
   constellation.rotation.y=Math.sin(time*.035)*.32;constellation.rotation.z=Math.sin(time*.018)*.065;
   constellation.position.set(camera.aspect>1?camera.aspect*1.35:0,.45,-.3);
   constellation.scale.setScalar(camera.aspect>1?1.05:.85);
  }
  const planeGeo=new THREE.PlaneGeometry(2,2);
  const nebulaMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,uniforms:{time:{value:0},aspect:{value:1}},vertexShader:`varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.999,1.0);}`,fragmentShader:`varying vec2 vUv;uniform float time;uniform float aspect;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}float fbm(vec2 p){float v=0.;float a=.5;for(int i=0;i<5;i++){v+=a*noise(p);p=p*2.02+vec2(12.3,6.1);a*=.5;}return v;}
void main(){vec2 p=vUv;vec2 q=vec2((p.x-.73)*aspect,p.y-.76);float n=fbm(q*3.+vec2(time*.015,time*.009));float cloud=exp(-length(q*vec2(.95,2.4))*2.2)*pow(n,2.0);float rim=exp(-abs(length((q+vec2(-.03,.35))*vec2(.78,1.55))-.5)*35.);rim*=smoothstep(-.25,.28,q.y);vec3 col=vec3(.24,.075,.52)*cloud*1.1+vec3(.38,.22,.65)*rim*.14;col+=vec3(.055,.15,.28)*exp(-length((q+vec2(.4,.05))*2.8))*n*.24;gl_FragColor=vec4(col,1.);}`});
  const nebula=new THREE.Mesh(planeGeo,nebulaMaterial);nebula.renderOrder=-1;scene.add(nebula);
  const resize=()=>{const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();nebulaMaterial.uniforms.aspect.value=w/h;needsFrame.current=true};resize();window.addEventListener('resize',resize);
  let frame=0,last=0,time=0;const tick=(now:number)=>{frame=requestAnimationFrame(tick);if(document.hidden||(!active.current&&!needsFrame.current)){last=now;return}if(now-last<32)return;const dt=Math.min((now-last)/1000,.05);last=now;if(active.current){time+=dt;stars.rotation.z=time*.002;stars.rotation.y=Math.sin(time*.025)*.025;nebulaMaterial.uniforms.time.value=time}drawConstellation(time);renderer.render(scene,camera);needsFrame.current=false};frame=requestAnimationFrame(tick);
  return()=>{cancelAnimationFrame(frame);window.removeEventListener('resize',resize);geo.dispose();material.dispose();planeGeo.dispose();nebulaMaterial.dispose();lineGeo.dispose();lineMaterial.dispose();nodeGeo.dispose();nodeMaterial.dispose();renderer.dispose();renderer.domElement.remove()};
 },[]);
 return <div ref={host} className="space-canvas" aria-hidden="true"/>;
}
