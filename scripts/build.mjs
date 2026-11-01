import {buildSeoPages,footer} from './seo-pages.mjs';
import {cp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';import path from 'node:path';import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
// On Windows `python3` is usually the Microsoft Store placeholder; PYTHON picks a specific interpreter.
execFileSync(process.env.PYTHON||(process.platform==='win32'?'python':'python3'),[path.join(root,'scripts/package-skill.py')],{stdio:'inherit'});
const films=JSON.parse(await readFile(path.join(root,'content/gallery.json'),'utf8'));
await writeFile(path.join(root,'site/gallery.json'),JSON.stringify(films,null,2));
await writeFile(path.join(root,'site/manifest.webmanifest'),JSON.stringify({name:'Narrate',short_name:'Narrate',start_url:'/',display:'standalone',background_color:'#f7f5ef',theme_color:'#f7f5ef',icons:[{src:'/assets/brand/mark.svg',sizes:'any',type:'image/svg+xml'},{src:'/assets/brand/apple-icon.png',sizes:'180x180',type:'image/png'}]},null,2));
const publicUrl=process.env.PUBLIC_SITE_URL?.replace(/\/$/,'');
if(publicUrl&&!/^https:\/\/[a-z0-9.-]+$/i.test(publicUrl))throw Error('PUBLIC_SITE_URL must be an HTTPS origin');
await writeFile(path.join(root,'site/robots.txt'),publicUrl?`User-agent: *\nAllow: /\nSitemap: ${publicUrl}/sitemap.xml\n`:'User-agent: *\nDisallow: /\n');
await writeFile(path.join(root,'site/sitemap.xml'),`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${publicUrl?['/','/guide.html'].map(route=>`<url><loc>${publicUrl}${route}</loc></url>`).join(''):''}</urlset>`);
await rm(path.join(root,'dist'),{recursive:true,force:true});await mkdir(path.join(root,'dist'));await cp(path.join(root,'site'),path.join(root,'dist'),{recursive:true});
if(publicUrl){
 let html=await readFile(path.join(root,'dist/index.html'),'utf8');
 const structured={"@context":"https://schema.org","@type":"SoftwareApplication",name:"Narrate",applicationCategory:"MultimediaApplication",operatingSystem:"macOS (Apple Silicon for bundled local speech)",url:publicUrl,codeRepository:"https://github.com/alibad/narrate",license:"https://github.com/alibad/narrate/blob/main/LICENSE",description:"A language-first local voice studio and narrated-video skill.",isPartOf:{"@type":"WebSite",name:"Human Quest AI Patterns",url:"https://www.humanquest.net/ai-patterns"},author:{"@type":"Organization",name:"Human Quest",url:"https://www.humanquest.net"},offers:{"@type":"Offer",price:"0",priceCurrency:"USD"}};
 html=html.replace('<meta property="og:image" content="/assets/brand/social.png">',`<meta property="og:image" content="${publicUrl}/assets/brand/social.png">`);
 html=html.replace('<meta name="twitter:image" content="/assets/brand/social.png">',`<meta name="twitter:image" content="${publicUrl}/assets/brand/social.png">`);
 html=html.replace('</head>',`<link rel="canonical" href="${publicUrl}/"><meta property="og:url" content="${publicUrl}/"><script type="application/ld+json">${JSON.stringify(structured)}</script></head>`);
 await writeFile(path.join(root,'dist/index.html'),html);
 let guide=await readFile(path.join(root,'dist/guide.html'),'utf8');
 guide=guide.replace('<body>',`<meta property="og:type" content="article"><meta property="og:title" content="Local setup — Narrate"><meta property="og:description" content="Choose languages, set up local voice models, record your voice and audition it."><meta property="og:url" content="${publicUrl}/guide.html"><meta property="og:image" content="${publicUrl}/assets/brand/social.png"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Local setup — Narrate"><meta name="twitter:description" content="Choose languages, set up local voice models, record your voice and audition it."><meta name="twitter:image" content="${publicUrl}/assets/brand/social.png"><meta name="description" content="Install Narrate, choose narration languages, set up a compatible local voice model, record your voice and audition it before rendering a video."><link rel="canonical" href="${publicUrl}/guide.html"><link rel="icon" href="/assets/brand/favicon.svg" type="image/svg+xml"><body>`);
 await writeFile(path.join(root,'dist/guide.html'),guide);
}
let guide=await readFile(path.join(root,'dist/guide.html'),'utf8');
await writeFile(path.join(root,'dist/guide.html'),guide.replace('</body>',footer+'</body>'));
await buildSeoPages(root,publicUrl||'',films);
console.log('Static site built. '+films.filter(f=>f.video).length+' playable films; '+films.length+' collection entries.');
