import test from 'node:test';
import assert from 'node:assert/strict';
import {CONSTELLATIONS,EDGE_SECONDS,HOLD_SECONDS,FADE_SECONDS,sampleConstellation} from '../frontend/src/constellations.mjs';
import {summarizeReadiness} from '../examples/flight-deck/src/metrics.mjs';

test('twelve distinct constellation graphs have safe, non-degenerate edges',()=>{
 assert.equal(CONSTELLATIONS.length,12);assert.equal(new Set(CONSTELLATIONS.map(s=>s.name)).size,12);
 for(const s of CONSTELLATIONS)for(const [a,b] of s.edges){assert(s.points[a]&&s.points[b]);assert.notDeepEqual(s.points[a],s.points[b])}
});
test('only one edge is constructed at a time with smooth endpoints',()=>{
 for(let n=0;n<10;n++){const s=sampleConstellation(n*EDGE_SECONDS+EDGE_SECONDS/2);assert.equal(s.completed,n);assert(Math.abs(s.progress-.5)<1e-10)}
 assert.equal(sampleConstellation(0).progress,0);assert.equal(sampleConstellation(EDGE_SECONDS).completed,1);
 assert(sampleConstellation(.001).progress<.00001);
});
test('shape holds, fades to zero and moves to the next graph without a jump',()=>{
 const duration=CONSTELLATIONS[0].edges.length*EDGE_SECONDS;
 assert.equal(sampleConstellation(duration+HOLD_SECONDS/2).opacity,1);
 assert.equal(sampleConstellation(duration+HOLD_SECONDS+FADE_SECONDS+.5).opacity,0);
 assert.equal(sampleConstellation(duration+HOLD_SECONDS+FADE_SECONDS+2).index,1);
 assert.equal(sampleConstellation(0,true).completed,CONSTELLATIONS[0].edges.length);
});
test('golden readiness semantics preserve empty data, percent units and rounding',()=>{
 const rows=[{program_id:'a',assembly_id:'1',readiness_pct:80},{program_id:'a',assembly_id:'2',readiness_pct:65}];
 assert.deepEqual(summarizeReadiness(rows),{visibleAssemblies:2,readiness:73});
 assert.deepEqual(summarizeReadiness([]),{visibleAssemblies:0,readiness:null});
 assert.deepEqual(summarizeReadiness([{...rows[0],readiness_pct:0}]),{visibleAssemblies:1,readiness:0});
});
test('golden tests reject duplicate grain, invalid units and partial results',()=>{
 const row={program_id:'a',assembly_id:'1',readiness_pct:80};
 assert.throws(()=>summarizeReadiness([row,row]),/Duplicate/);
 for(const value of [null,NaN,Infinity,'80',-1,101])assert.throws(()=>summarizeReadiness([{...row,readiness_pct:value}]),/percent/);
 assert.throws(()=>summarizeReadiness([row],true),/Partial/);
 assert.throws(()=>summarizeReadiness([{readiness_pct:80}]),/key/);
});
