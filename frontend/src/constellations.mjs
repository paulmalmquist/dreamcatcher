// Slow, deterministic aerospace/analytics motion. No timers or WebGL in this module.
// Each edge finishes before the next begins; a cycle includes a hold and fade.
const shape=(name,points,edges)=>({name,points:points.map(([x,y,z=0])=>[x,y,z]),edges});
export const CONSTELLATIONS=[
 shape('Launch vehicle',[[0,1.5],[-.38,.8],[-.38,-.7],[.38,-.7],[.38,.8],[-.85,-1.05],[.85,-1.05],[-.18,-1.4],[0,-1.12],[.18,-1.4]],[[0,1],[1,2],[2,3],[3,4],[4,0],[2,5],[5,1],[3,6],[6,4],[2,7],[7,8],[8,9],[9,3]]),
 shape('Avionics circuit',[[-.7,.7],[.7,.7],[.7,-.7],[-.7,-.7],[-1.25,.35],[-.7,.35],[-1.25,-.35],[-.7,-.35],[.7,.35],[1.25,.35],[.7,-.35],[1.25,-.35],[-.3,1.2],[-.3,.7],[.3,-.7],[.3,-1.2]],[[0,1],[1,2],[2,3],[3,0],[4,5],[6,7],[8,9],[10,11],[12,13],[14,15],[0,2]]),
 shape('Orbital path',[[0,1],[-1,.55],[-1.3,-.2],[-.7,-.8],[.3,-1],[1.15,-.45],[1.3,.3],[.6,.85],[0,0]],[[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7],[7,0],[8,0],[8,4]]),
 shape('Engine nozzle',[[-.5,1],[.5,1],[.3,.35],[.28,-.2],[.9,-1],[-.9,-1],[-.28,-.2],[-.3,.35],[0,-1.4]],[[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7],[7,0],[7,2],[6,3],[5,8],[8,4]]),
 shape('Satellite',[[-.35,.5],[.35,.5],[.35,-.5],[-.35,-.5],[-1.3,.65],[-1.3,-.65],[1.3,.65],[1.3,-.65],[0,1.2]],[[0,1],[1,2],[2,3],[3,0],[0,4],[4,5],[5,3],[1,6],[6,7],[7,2],[0,8],[8,1]]),
 shape('Telemetry trace',[[-1.4,-.8],[-1.4,1],[-1,-.4],[-.65,-.35],[-.4,.8],[-.15,-.7],[.15,.35],[.45,-.1],[.85,.5],[1.4,.35],[1.4,-.8]],[[1,0],[0,10],[2,3],[3,4],[4,5],[5,6],[6,7],[7,8],[8,9]]),
 shape('Supply network',[[-1.3,.6],[-1.3,-.6],[0,.9],[0,0],[0,-.9],[1.3,.6],[1.3,-.6]],[[0,2],[0,3],[1,3],[1,4],[2,5],[3,5],[3,6],[4,6],[2,3],[3,4]]),
 shape('Manufacturing cell',[[-1,-1],[1,-1],[1,1],[-1,1],[-.7,-.55],[-.3,.05],[.3,.5],[.75,.1],[.45,-.25],[.1,-.1]],[[0,1],[1,2],[2,3],[3,0],[0,4],[4,5],[5,6],[6,7],[7,8],[8,9]]),
 shape('Digital thread',[[-1.25,1],[-.5,.5],[.4,1],[1.25,.5],[-1.25,-.2],[-.5,-.7],[.4,-.2],[1.25,-.7]],[[0,1],[1,2],[2,3],[0,4],[1,5],[2,6],[3,7],[4,5],[5,6],[6,7]]),
 shape('Readiness bars',[[-1.3,-1],[1.3,-1],[-1,0],[-.5,0],[-.5,-1],[-1,-1],[-.2,.5],[.3,.5],[.3,-1],[-.2,-1],[.6,1],[1.1,1],[1.1,-1],[.6,-1]],[[0,1],[5,2],[2,3],[3,4],[9,6],[6,7],[7,8],[13,10],[10,11],[11,12]]),
 shape('Quality checkpoint',[[0,1.3],[1,.8],[.8,-.6],[0,-1.2],[-.8,-.6],[-1,.8],[-.5,.1],[-.12,-.3],[.6,.45]],[[0,1],[1,2],[2,3],[3,4],[4,5],[5,0],[6,7],[7,8]]),
 shape('Mission trajectory',[[-1.2,-1],[-.8,-.3],[-.4,.3],[.1,.8],[.75,1.05],[1.3,1.1],[-1.2,1.1],[1.3,-1]],[[0,7],[0,6],[0,1],[1,2],[2,3],[3,4],[4,5]])
];
export const EDGE_SECONDS=1.8;
export const HOLD_SECONDS=7;
export const FADE_SECONDS=3;
const GAP_SECONDS=2;
const smooth=t=>t*t*(3-2*t);
export function sampleConstellation(seconds,still=false){
 const lengths=CONSTELLATIONS.map(s=>s.edges.length*EDGE_SECONDS+HOLD_SECONDS+FADE_SECONDS+GAP_SECONDS);
 let phase=Math.max(0,seconds)%lengths.reduce((a,b)=>a+b,0),index=0;
 while(phase>=lengths[index])phase-=lengths[index++];
 const current=CONSTELLATIONS[index],build=current.edges.length*EDGE_SECONDS;
 if(still)return {index,shape:current,completed:current.edges.length,progress:0,opacity:.7};
 const completed=Math.min(current.edges.length,Math.floor(phase/EDGE_SECONDS));
 const progress=completed<current.edges.length?smooth((phase-completed*EDGE_SECONDS)/EDGE_SECONDS):0;
 const opacity=phase<build+HOLD_SECONDS?Math.min(1,phase/1.5):1-smooth(Math.min(1,(phase-build-HOLD_SECONDS)/FADE_SECONDS));
 return {index,shape:current,completed,progress,opacity};
}
