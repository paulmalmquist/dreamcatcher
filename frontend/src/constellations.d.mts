export type Constellation={name:string;points:[number,number,number][];edges:[number,number][]};
export const CONSTELLATIONS:Constellation[];
export const EDGE_SECONDS:number;
export const HOLD_SECONDS:number;
export const FADE_SECONDS:number;
export function sampleConstellation(seconds:number,still?:boolean):{index:number;shape:Constellation;completed:number;progress:number;opacity:number};
