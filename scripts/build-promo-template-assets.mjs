import {mkdir, readFile, writeFile, copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import sharp from 'sharp';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base=path.join(root,'services/worker/src/demodirector_worker/templates');
const requestedTheme=(process.argv.find(value=>value.startsWith('--theme='))||'--theme=default').slice('--theme='.length);
const THEMES={
 default:{label:'Editorial',suffix:'',green:'#234D44',ink:'#0A211C',mint:'#9DE8D2',ivory:'#F3EDE1',line:'#73BDAA',coral:'#FF796C'},
 google:{label:'Google-inspired blue and red',suffix:'-google',green:'#1A73E8',ink:'#202124',mint:'#FF6666',ivory:'#FFFFFF',line:'#34A853',coral:'#FF6666'},
};
const C=THEMES[requestedTheme];
if(!C) throw new Error(`Unknown template theme: ${requestedTheme}`);
const xml=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;');
const rect=(r,fill,extra='')=>`<rect x="${r.x}" y="${r.y}" width="${r.width}" height="${r.height}" fill="${fill}" ${extra}/>`;
const docs=[];
for(const mode of ['spotlight','short']) for(const orientation of ['landscape','vertical']) {
 const vertical=orientation==='vertical', W=vertical?1080:2560,H=vertical?1920:1440;
 const phoneShort=mode==='short'&&vertical;
 const referenceShort=phoneShort&&requestedTheme==='google';
 const folder=path.join(base,`${mode}-${orientation}${C.suffix}-v1`); await mkdir(path.join(folder,'shared'),{recursive:true});
 await copyFile(path.join(base,'presentation-story-v2/shared/inter-latin-variable.woff2'),path.join(folder,'shared/inter-latin-variable.woff2'));
 await copyFile(path.join(root,'node_modules/@fontsource-variable/inter/LICENSE'),path.join(folder,'shared/LICENSE'));
 const svg=body=>`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${body}</svg>`;
 const slots=(id,x,y,width,height,font,max,maxlines=1)=>({id,rect:{x,y,width,height},font_token:font,max_characters:max,max_lines:maxlines,align:'left',color:C.ivory});
 const tokens={brand:{size:vertical?34:38,line_height:48,weight:500,tracking:0},headline:{size:vertical?66:100,line_height:vertical?78:112,weight:600,tracking:-1},body:{size:vertical?38:48,line_height:vertical?50:60,weight:400,tracking:0},cta:{size:vertical?54:72,line_height:vertical?68:86,weight:500,tracking:-1}};
 if(phoneShort){tokens.brand={size:54,line_height:64,weight:600,tracking:0};tokens.body={size:48,line_height:62,weight:500,tracking:0};}
 const caption={x:phoneShort?88:vertical?72:500,y:phoneShort?1418:vertical?1630:1252,width:phoneShort?904:vertical?840:1560,height:104,words_per_line:vertical?3:7};
 if(phoneShort)Object.assign(caption,{text_color:C.ink,highlight_background:C.ivory,highlight_color:C.ink});
 if(referenceShort)caption.y=1530;
 const stages=mode==='spotlight'?[['hook',4,'title'],['proof',22,'search'],['close',4,'title']]:[['hook',4,'title'],['search',12,'search'],['context',12,'article'],['related',12,'related'],['close',5,'title']];
 const templates=[],schedule=[]; let cursor=0;
 for(const [stage,seconds,recipe] of stages){
  const id=`${mode}-${stage}@${requestedTheme==='default'?'1':`${requestedTheme}-1`}`,assetdir=`slides/${stage}`;await mkdir(path.join(folder,assetdir),{recursive:true});
  const product=recipe!=='title',close=stage==='close';
  const aperture=phoneShort?{x:56,y:480,width:968,height:870,corner_radius:0}:vertical?{x:72,y:470,width:840,height:1090,corner_radius:10}:{x:128,y:330,width:2304,height:860,corner_radius:10};
  if(referenceShort)Object.assign(aperture,{y:500,height:902,corner_radius:32});
  const copy=[slots('brand',vertical?72:128,vertical?150:86,vertical?840:2000,60,'brand',32)];
  if(product){copy.push(slots('headline',vertical?72:128,vertical?250:175,vertical?840:2304,vertical?160:130,mode==='short'?'body':'headline',mode==='short'?100:(vertical?40:54),vertical?2:(mode==='short'?2:1)));}
  else {copy.push(slots('headline',vertical?72:128,vertical?450:330,vertical?840:2200,vertical?390:360,'headline',60,3));copy.push(slots(close?'cta':'body',vertical?72:128,vertical?1030:790,vertical?840:2100,vertical?240:180,close?'cta':'body',close?46:90,3));}
  if(phoneShort){
   copy[0]=slots('brand',100,160,880,64,'brand',32);
   if(product)copy[1]=slots('headline',100,274,880,152,'body',72,2);
  }
  if(referenceShort){
   copy[0]=slots('brand',570,310,420,124,'brand',16,2);
   if(product)copy[1]=slots('headline',100,120,880,124,'body',58,2);
   else {
    copy[1]=slots('headline',100,650,880,330,'headline',60,3);
    copy[2]=slots(close?'cta':'body',100,1050,880,240,close?'cta':'body',close?46:90,3);
   }
  }
  const sample=product?{brand:'Your product',headline:mode==='spotlight'?'One feature. See it work.':({search:'Ask a question, then watch the answer take shape.',context:'Read the detail without losing the bigger picture.',related:'Follow one useful connection to the next.'}[stage])}:{brand:'Your product',headline:close?'Make your next move.':mode==='spotlight'?'Show the feature.\nMake the benefit clear.':'Meet your product.\nIn under a minute.',[close?'cta':'body']:close?'Explore your product':'A concise story, grounded in real product footage.'};
  if(phoneShort&&product)sample.headline=({search:'Ask a question.\nSee the answer take shape.',context:'Read the detail.\nKeep the bigger picture.',related:'Find a connection.\nFollow it further.'}[stage]);
  let background=rect({x:0,y:0,width:W,height:H},C.green);
  if(!product)background+=rect({x:vertical?72:128,y:vertical?365:245,width:vertical?100:140,height:8},C.mint);
  else background+=rect(aperture,C.ink,'rx="10"');
  if(mode==='short'&&product)background+=rect({x:vertical?72:128,y:vertical?438:306,width:vertical?840:2304,height:2},C.ivory,'opacity="0.36"');
  background+=rect({x:caption.x,y:caption.y,width:caption.width,height:104},C.ink,'rx="8"');
  if(phoneShort){
   background=rect({x:0,y:0,width:W,height:H},C.ink);
   background+=rect({x:56,y:80,width:968,height:400},C.green);
   background+=rect({x:56,y:1350,width:968,height:240},C.coral);
   background+=rect({x:56,y:1590,width:12,height:150},C.green);
   if(product)background+=rect(aperture,C.ink);
   else background+=rect({x:56,y:480,width:968,height:870},C.green);
  }
  if(referenceShort){
   background=rect({x:0,y:0,width:W,height:H},'#000');
   background+=rect({x:56,y:86,width:968,height:414},C.green,'rx="32"');
   background+=rect({x:570,y:402,width:454,height:98},'#000');
   background+=rect({x:570,y:402,width:116,height:88},'#fff');
   background+=rect({x:338,y:274,width:216,height:226},'#000','rx="20"');
   background+=`<path d="M382 318 H414 L446 393 L478 318 H510 L446 456 Z" fill="${C.coral}"/>`;
   background+=rect({x:56,y:1402,width:968,height:270},C.coral,'rx="32"');
   background+=rect({x:56,y:1402,width:318,height:92},'#000');
   background+=rect({x:374,y:1402,width:120,height:92},'#fff');
   background+=rect({x:56,y:1672,width:14,height:154},C.coral);
   background+=rect(aperture,product?'#000':C.green,'rx="32"');
  }
  const foreground=product&&!phoneShort?rect(aperture,'none',`rx="10" stroke="${C.line}" stroke-width="3"`):'';
  const toPng=async(body,file)=>writeFile(path.join(folder,assetdir,file),await sharp(Buffer.from(svg(body))).png().toBuffer());
  await toPng(background,'background.png');await toPng(foreground,'foreground.png');
  if(product) await writeFile(path.join(folder,assetdir,'product-mask.png'),await sharp(Buffer.from(svg(rect({x:0,y:0,width:W,height:H},'#000')+rect(aperture,'#fff',`rx="${aperture.corner_radius}"`)))).greyscale().png().toBuffer());
  const specimen=copy.map(s=>{const token=tokens[s.font_token];return (sample[s.id]||'').split('\n').map((line,i)=>`<text x="${s.rect.x}" y="${s.rect.y+token.size+i*token.line_height}" fill="${s.color}" font-family="sans-serif" font-size="${token.size}" font-weight="${token.weight}">${xml(line)}</text>`).join('');}).join('');
  const footage=product?(phoneShort?rect(aperture,C.ivory,'opacity="0.08"')+`<text x="${W/2}" y="${aperture.y+aperture.height/2}" text-anchor="middle" fill="${C.ivory}" font-family="sans-serif" font-size="44">Product recording</text>`:`<text x="${aperture.x+40}" y="${aperture.y+aperture.height/2}" fill="${C.mint}" font-family="sans-serif" font-size="${vertical?36:48}">Real feature recording</text>`):'';
  const narrationSample=phoneShort?`<text x="${W/2}" y="${caption.y+69}" text-anchor="middle" fill="${C.ink}" font-family="sans-serif" font-size="44">Watch each step unfold.</text>`:'';
  const clippedFootage=referenceShort?`<defs><clipPath id="product-window">${rect(aperture,'#fff','rx="32"')}</clipPath></defs><g clip-path="url(#product-window)">${footage}</g>`:footage;
  const source=svg(background+foreground+specimen+clippedFootage+narrationSample);
  await writeFile(path.join(folder,assetdir,'source.svg'),source);
  await writeFile(path.join(folder,assetdir,'preview.png'),await sharp(Buffer.from(source)).resize({width:vertical?432:1024}).png().toBuffer());
  templates.push({id,name:`${C.label} ${mode} ${stage}`,canvas:{width:W,height:H},role:stage,story_intent:mode==='spotlight'?'Demonstrate exactly one feature and its grounded benefit.':'Use a concise top brief, a central product recording, and bottom narration to introduce connected capabilities.',requires_product:product,product_aperture:product?aperture:null,copy_slots:copy,visual_revision:`${mode}-${orientation}-${requestedTheme}-${mode==='short'?'2':'1'}`,assets:{background_png:`${assetdir}/background.png`,foreground_png:`${assetdir}/foreground.png`,...(product?{product_mask_png:`${assetdir}/product-mask.png`}:{})}});
  if(referenceShort)templates.at(-1).visual_revision='short-vertical-google-rounded-3';
  schedule.push({template_id:id,start_ms:cursor,end_ms:cursor+seconds*1000,recipe});cursor+=seconds*1000;
 }
 const integrity={};for(const t of templates)for(const file of Object.values(t.assets)){integrity[file]=createHash('sha256').update(await readFile(path.join(folder,file))).digest('hex');}
 integrity['shared/inter-latin-variable.woff2']=createHash('sha256').update(await readFile(path.join(folder,'shared/inter-latin-variable.woff2'))).digest('hex');
 await writeFile(path.join(folder,'manifest.json'),JSON.stringify({pack_id:`${mode}-${orientation}-${requestedTheme}@1`,display_name:`${C.label} ${mode} demo`,family:'promo',mode:`${mode}_demo`,theme:requestedTheme,canvas:{width:W,height:H},caption_layout:caption,typography:{tokens},templates,schedule,integrity:{files:integrity}},null,2));
 if(phoneShort){
  const rendered=spawnSync(process.execPath,[path.join(root,'scripts/python-runner.mjs'),path.join(root,'scripts/render-promo-previews.py'),folder],{cwd:root,stdio:'inherit'});
  if(rendered.status!==0)throw new Error('Portrait template previews could not be rendered.');
  if(requestedTheme==='default')await copyFile(path.join(folder,'slides/search/preview.png'),path.join(root,'apps/web/public/examples/short-vertical.png'));
 }
 docs.push({mode,orientation,folder: path.relative(base,folder),stages:stages.map(x=>x[0])});
}
await writeFile(path.join(base,requestedTheme==='default'?'promo-templates.html':`promo-${requestedTheme}-templates.html`),`<!doctype html><meta charset="utf-8"><title>${C.label} Spotlight and Short templates</title><style>body{background:${C.ink};color:${C.ivory};font:18px system-ui;margin:40px}h1{font-size:30px}h2{font-size:22px}section{display:flex;gap:16px;overflow:auto;padding-bottom:20px}figure{margin:0}img{height:270px;border:1px solid ${C.line}}figcaption{padding:8px 0;color:${C.mint}}</style><h1>${C.label} Spotlight and Short</h1><p>Template specimens. Product copy is generated by Gemini / ADK at runtime.</p>${docs.map(d=>`<h2>${d.mode} / ${d.orientation}</h2><section>${d.stages.map(s=>`<figure><img src="${d.folder}/slides/${s}/preview.png"><figcaption>${s}</figcaption></figure>`).join('')}</section>`).join('')}`);
console.log(`Built four ${C.label} promo template packs.`);
