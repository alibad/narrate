export function recommend(catalog,languages,existing='',preference='reuse'){
 if(!Array.isArray(languages)||languages.length>12||languages.some(code=>!catalog.languages.some(l=>l.code===code)))throw Error('Choose up to 12 documented languages');
 if(!['reuse','compact'].includes(preference))throw Error('Unknown setup preference');
 const selected=[...new Set(languages)];
 const models=catalog.models.map(m=>{const missing=selected.filter(c=>!m.languages.includes(c));const present=m.id===existing;return {...m,missing,present,eligible:!missing.length,score:(preference==='reuse'&&present?200:0)-m.bytes/1e9}}).sort((a,b)=>Number(b.eligible)-Number(a.eligible)||b.score-a.score);
 return {models,best:selected.length?models.find(m=>m.eligible):null};
}
