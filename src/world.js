'use strict';
const $=id=>document.getElementById(id),empty=()=>({type:'FeatureCollection',features:[]});
const levels={green:'Normal vigilance',yellow:'Heightened caution',orange:'Travel discouraged unless essential',red:'Travel strongly discouraged'};
const palette=['match',['get','risk'],'green','#c2d764','yellow','#fff7b2','orange','#f5a04d','red','#e0181b','#dce3e6'];
const providers={france_diplomatie:'France Diplomatie',uk_fcdo:'UK Foreign, Commonwealth & Development Office'};
const requests=new Map();
function json(url){if(!requests.has(url))requests.set(url,fetch(url).then(r=>{if(!r.ok)throw Error(`Could not load ${url} (${r.status})`);return r.json();}).catch(e=>{requests.delete(url);throw e;}));return requests.get(url);}
function notify(text){$('announcement').textContent=text;}
function fail(error){$('map-note').textContent=error.message;notify(error.message);console.error(error);}
const clean=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const initial=new URLSearchParams(location.hash.slice(1));
let manifest,catalogue,selected=null,selectedCity=null,selectedZone=null,generation=0,selectionRequest=0,major=[],placeCache=new Map(),detailCache=new Map(),overviewCache=[],exceptions=[],searchCities=null;
const map=new maplibregl.Map({container:'map',center:[16,22],zoom:1,maxZoom:11,minZoom:-1,renderWorldCopies:false,transformConstrain:(center,zoom)=>({center:new maplibregl.LngLat(Math.max(-180,Math.min(180,center.lng)),Math.max(-85,Math.min(85,center.lat))),zoom:Math.max(-1,Math.min(11,zoom))}),attributionControl:false,style:{version:8,glyphs:'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',sources:{},layers:[{id:'ocean',type:'background',paint:{'background-color':'#eaf1f4'}}]}});
map.addControl(new maplibregl.NavigationControl({showCompass:false}));
map.addControl(new maplibregl.AttributionControl({customAttribution:'Natural Earth · France Diplomatie · UK FCDO · Independent preview',compact:true}));
function source(id,data){map.getSource(id).setData(data);}
function filter(id,value){map.setFilter(id,value);}
function dataFor(iso){return manifest?.countries[iso];}
function highlight(){filter('selected-country',['==',['get','iso3'],selected||'']);filter('selected-city',['==',['get','id'],selectedCity||'']);}
function updateHash(){if(!manifest)return;const c=map.getCenter();const q=new URLSearchParams({snapshot:manifest.date,z:map.getZoom().toFixed(2),lat:c.lat.toFixed(4),lng:c.lng.toFixed(4)});if(selected)q.set('country',selected);if(selectedCity)q.set('city',selectedCity);if(selectedZone)q.set('zone',selectedZone);history.replaceState(null,'','#'+q.toString());}
function bounds(row){const b=row.bounds;return [[b[0],Math.max(-80,b[1])],[b[2],Math.min(84,b[3])]];}
function fit(iso){map.fitBounds(bounds(dataFor(iso)),{padding:45,maxZoom:8,duration:0});}
function fitWorld(){map.fitBounds([[-180,-60],[180,83.8]],{padding:20,duration:0,maxZoom:2});}
function reset(){selected=null;selectedCity=null;selectedZone=null;selectionRequest++;$('overview').hidden=false;$('selection').hidden=true;$('clear').hidden=true;highlight();updateHash();}
function setLink(id,url){const el=$(id);el.hidden=!url;if(url)el.href=url;else el.removeAttribute('href');}
function fillDates(items){$('dates').replaceChildren(...items.filter(x=>x[1]).map(([label,value])=>{const span=document.createElement('span');span.textContent=`${label}: ${value}`;return span;}));}
function updateNote(){if(!manifest)return;const row=dataFor(selected);const detailed=row?.detail&&map.getZoom()>=6;const local=row?.local_overview&&map.getZoom()<6;$('map-note').textContent=detailed||local?'Country map · simplified zones · capitals are squares':map.getZoom()>=5?'World overview · coarse boundaries at this zoom':'World overview · select a country or search for a city';}
async function choose(iso,feature=null,fly=false){
 const row=dataFor(iso);if(!row)return;const token=++selectionRequest;
 selected=iso;selectedCity=null;selectedZone=feature?.zone_id||null;
 $('overview').hidden=true;$('selection').hidden=false;$('clear').hidden=false;$('country').textContent=row.name;$('city-card').hidden=true;
 const p=feature||{},countryMap=p.resolution==='country_map'||(!feature&&row.local_overview);
 $('risk').textContent=p.risk?levels[p.risk]+(p.restriction?' · Closed to civilians':''):row.overview?'Regional advice varies · click a coloured zone':'No French risk zones mapped here';
 $('provider').textContent='Loading official advice…';$('context').textContent='';$('topics').replaceChildren();$('context-scope').textContent='';$('advice-status').textContent='';setLink('source',null);
 $('geometry-note').textContent=row.overview?countryMap?'Geometry: France Diplomatie country map. Other areas may use the coarser world overview.':'Geometry: France Diplomatie world overview; approximate sub-country boundaries.':'No zone classification is inferred from the presence of an advice page.';
 $('coverage-detail').textContent=`Approximately ${Math.round(row.coverage_fraction*100)}% of this display boundary is covered by the world extraction.${row.detail?' A more detailed country layer is also available.':''} Small islands, insets and some coastline gaps remain unresolved.`;
 setLink('map-source',countryMap?row.detail_source.map_url:row.geometry_source.url);
 const changed=manifest.changes.find(c=>c.iso3===iso);$('change-note').hidden=!changed;$('change-note').textContent=changed?`${changed.kind==='new_coverage'?'New coverage':'Since '+manifest.previous_snapshot}: ${changed.reasons.join('; ')}. This is not by itself a change in travel risk.`:'';
 highlight();if(fly)fit(iso);updateHash();updateNote();
 try{
  const advice=row.advice?await json(row.advice):null;if(token!==selectionRequest)return;
  const allowed=advice&&($('fallbacks').checked||advice.provider!=='uk_fcdo');
  $('provider').textContent=allowed?providers[advice.provider]+(advice.provider==='uk_fcdo'?' · fallback advice':''):'No dedicated advice shown';
  const context=allowed?advice.context:null;
  $('context').textContent=context?.text||'Open the official source for the full assessment. No reviewed short excerpt is available for this selection.';
  $('context-scope').textContent=context?`Country-level source excerpt · ${context.language==='fr'?'French':'English'}${advice.page_title&&clean(advice.page_title)!==clean(row.name)?' · '+advice.page_title:''}. It does not explain every individual zone.`:'';
  $('topics').replaceChildren(...(context?.topics||[]).map(t=>{const span=document.createElement('span');span.textContent=t;return span;}));
  if(allowed&&advice.provider==='uk_fcdo')$('advice-status').textContent=advice.alert_status.length?'UK alert flags: '+advice.alert_status.map(t=>t.replaceAll('_',' ')).join('; '):'UK guidance has no whole-country or regional “against travel” flag in this snapshot. This is not a French green rating.';
  if(allowed&&row.source_check_error)$('advice-status').textContent+=' Source refresh failed; showing the last successful check.';
  if(!allowed)$('advice-status').textContent=advice?'Other-government advice is switched off.':'No dedicated country advice page has been matched for this territory.';
  setLink('source',allowed?advice.url:null);$('source').textContent=allowed&&advice.provider==='uk_fcdo'?'Read UK government advice ↗':'Read French government advice ↗';
  fillDates([['Advice updated',allowed?advice.updated_label:null],['Source checked',allowed?(row.advice_checked_at||advice.checked_at).slice(0,10):null],['Map date',countryMap?row.detail_source.map_date:row.geometry_source.map_date],['Snapshot',manifest.date]]);
 }catch(e){if(token===selectionRequest){$('provider').textContent='Advice could not be loaded';$('context').textContent='The local source file could not be loaded. Please retry the selection.';}fail(e);}
}
async function selectCity(f,fly=false){f=exceptions.find(e=>e.properties.iso3===f.properties.iso3&&clean(e.properties.name)===clean(f.properties.name))||f;const p=f.properties;await choose(p.iso3,null,false);if(selected!==p.iso3)return;selectedCity=p.id;selectedZone=null;highlight();const title=document.createElement('strong');title.textContent=p.name;const text=document.createElement('p');text.textContent=p.kind==='city_exception'?`${levels[p.risk]}. ${p.condition} The point does not define an area or a safe access route.`:p.capital?'Capital · square location marker. It does not carry a separate risk rating.':'City location · its marker does not carry a separate risk rating.';$('city-card').replaceChildren(title,text);$('city-card').hidden=false;if(fly)map.jumpTo({center:f.geometry.coordinates,zoom:7});updateHash();}
function renderCities(){const all=new Map(major.map(f=>[f.properties.id,f]));for(const data of placeCache.values())for(const f of data.features)all.set(f.properties.id,f);for(const f of exceptions){for(const [id,other] of all)if(other.properties.iso3===f.properties.iso3&&clean(other.properties.name)===clean(f.properties.name))all.delete(id);all.set(f.properties.id,f);}source('places',{type:'FeatureCollection',features:[...all.values()]});}
let loadingViewport=false,viewportQueued=false;
async function viewportData(){if(!manifest||map.getZoom()<5)return;if(loadingViewport){viewportQueued=true;return;}loadingViewport=true;const version=generation;
 try{const visible=[...new Set([selected,...map.queryRenderedFeatures({layers:['land']}).map(f=>f.properties.iso3)])].filter(iso=>dataFor(iso)).slice(0,24);
  await Promise.all(visible.map(async iso=>{const row=dataFor(iso);if(!placeCache.has(iso)){const data=await json(row.places);if(version===generation)placeCache.set(iso,data);}if(map.getZoom()>=6&&row.detail&&!detailCache.has(iso)){const data=await json(row.detail);if(version===generation)detailCache.set(iso,data);}}));
  if(version===generation){renderCities();source('detail',{type:'FeatureCollection',features:[...detailCache.values()].flatMap(d=>d.features)});}
 }catch(e){fail(e);}finally{loadingViewport=false;if(viewportQueued){viewportQueued=false;viewportData();}}}
function changes(){const ids=$('changes').checked?manifest.changes.map(c=>c.iso3):[];filter('changes',['in',['get','iso3'],['literal',ids]]);}
async function loadSnapshot(day,restore=false){$('search').disabled=true;const version=++generation;selectionRequest++;const m=await json(`snapshots/${day}.json`);if(version!==generation)return;manifest=m;placeCache=new Map();detailCache=new Map();overviewCache=[];exceptions=[];searchCities=null;selected=null;selectedCity=null;selectedZone=null;
 const [land,zones,places,fallback]=await Promise.all([json(m.land),json(m.overview),json(m.major_places),json(m.fallback_land)]);if(version!==generation)return;
 major=places.features;source('land',land);source('overview',zones);source('fallback',fallback);source('local',empty());source('detail',empty());source('places',places);reset();
 $('snapshot').value=day;$('changes').disabled=!m.previous_snapshot;$('changes').checked=false;changes();$('changes').title=m.previous_snapshot?`Compare with ${m.previous_snapshot}`:'The first worldwide snapshot is the baseline; no earlier world snapshot exists.';
 $('baseline').textContent=m.previous_snapshot?`Changes compare with ${m.previous_snapshot}. New coverage is listed separately from changed source content.`:'First worldwide snapshot. Monthly comparisons will appear when a second snapshot is recorded.';
 const stats=[[m.source_coverage.france_diplomatie,'French advice records'],[m.source_coverage.uk_fallback,'UK fallback records'],[m.geometry_coverage.detailed_countries,'Detailed country layers'],[m.geometry_coverage.city_count.toLocaleString(),'Named places']];$('coverage').replaceChildren(...stats.map(([n,label])=>{const div=document.createElement('div'),strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=n;small.textContent=label;div.append(strong,small);return div;}));
 const age=Math.max(0,Math.floor((Date.now()-Date.parse(day+'T00:00:00Z'))/86400000));$('freshness').textContent=`Snapshot ${day} UTC · ${age} day${age===1?'':'s'} old${age>35?' · Update overdue':''} · World image ${m.world_source.map_date}`;
 await Promise.all(Object.values(m.countries).filter(c=>c.local_overview).map(async c=>{const data=await json(c.local_overview);if(version===generation)overviewCache.push(...data.features);if(c.exceptions){const points=await json(c.exceptions);if(version===generation)exceptions.push(...points.features);}}));if(version!==generation)return;source('local',{type:'FeatureCollection',features:overviewCache});renderCities();
 if(restore){const iso=initial.get('country');if(dataFor(iso)){const zone=[...overviewCache,...zones.features].find(f=>f.properties.iso3===iso&&f.properties.zone_id===initial.get('zone'));await choose(iso,zone?.properties||null,false);selectedZone=initial.get('zone');selectedCity=initial.get('city');highlight();}const z=Number(initial.get('z')),lat=Number(initial.get('lat')),lng=Number(initial.get('lng'));if(initial.has('z')&&[z,lat,lng].every(Number.isFinite)&&Math.abs(lat)<=85&&Math.abs(lng)<=540)map.jumpTo({center:[lng,lat],zoom:Math.max(-1,Math.min(11,z))});else if(iso&&dataFor(iso))fit(iso);else fitWorld();if(selectedCity&&selected){const points=await json(dataFor(selected).places);const f=points.features.find(f=>f.properties.id===selectedCity)||exceptions.find(f=>f.properties.id===selectedCity);if(f)await selectCity(f,false);}}
 updateNote();updateHash();$('search').disabled=false;await viewportData();
}
async function search(){const text=clean($('search').value.trim());if(!text||!manifest){$('results').hidden=true;$('search').setAttribute('aria-expanded','false');return;}const version=generation;
 if(!searchCities){const data=await json(manifest.search_index);if(version!==generation)return;searchCities=data.cities.map(c=>[...c]);for(const f of exceptions){const p=f.properties,row=[p.id,p.name,p.iso3,...f.geometry.coordinates,false],index=searchCities.findIndex(c=>c[2]===p.iso3&&clean(c[1])===clean(p.name));if(index<0)searchCities.push(row);else searchCities[index]=row;}}
 const q=clean($('search').value.trim());if(!q)return;
 const countries=Object.values(manifest.countries).filter(c=>clean(c.name+' '+(c.french_name||'')).includes(q)).sort((a,b)=>Number(clean(b.name).startsWith(q))-Number(clean(a.name).startsWith(q))).slice(0,6).map(c=>({label:c.name,sub:'Country / territory',run:()=>choose(c.iso3,null,true)}));
 const cities=searchCities.filter(c=>clean(c[1]).includes(q)).sort((a,b)=>Number(clean(b[1])===q)-Number(clean(a[1])===q)||Number(b[5])-Number(a[5])||(major.find(f=>f.properties.id===a[0])?.properties.priority||999999999)-(major.find(f=>f.properties.id===b[0])?.properties.priority||999999999)).slice(0,6).map(c=>({label:c[1],sub:manifest.countries[c[2]]?.name||c[2],run:()=>selectCity({type:'Feature',properties:{id:c[0],name:c[1],iso3:c[2],capital:c[5],kind:'city'},geometry:{type:'Point',coordinates:[c[3],c[4]]}},true)}));
 $('results').replaceChildren(...[...countries,...cities].map(item=>{const b=document.createElement('button');b.setAttribute('role','option');const label=document.createElement('span'),sub=document.createElement('small');label.textContent=item.label;sub.textContent=item.sub;b.append(label,sub);b.onclick=()=>{$('results').hidden=true;$('search').setAttribute('aria-expanded','false');$('search').value=item.label;item.run().catch(fail);};return b;}));if(!countries.length&&!cities.length){const p=document.createElement('p');p.textContent='No matching place';p.style.padding='0 12px';$('results').append(p);}$('results').hidden=false;$('search').setAttribute('aria-expanded','true');
}
map.on('load',async()=>{try{
 for(const id of ['land','fallback','overview','local','detail','places'])map.addSource(id,{type:'geojson',data:empty(),tolerance:.4});
 map.addLayer({id:'land',source:'land',type:'fill',paint:{'fill-color':'#dce3e6','fill-outline-color':'#bbc8cf'}});
 map.addLayer({id:'fallback',source:'fallback',type:'fill',paint:{'fill-color':'#a6b7c4','fill-opacity':.8}});
 for(const [id,range] of [['overview',{}],['local',{maxzoom:6}],['detail',{minzoom:6}]]){
  map.addLayer({id,source:id,type:'fill',...range,paint:{'fill-color':palette,'fill-opacity':.91}});
  map.addLayer({id:'restriction-'+id,source:id,type:'fill',...range,filter:['==',['get','restriction'],'closed_to_civilians'],paint:{'fill-color':'#49364f','fill-opacity':1}});
 }
 map.addLayer({id:'country-borders',source:'land',type:'line',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#52646c','line-opacity':.7,'line-width':['interpolate',['linear'],['zoom'],0,.35,4,.55,8,.8,11,1]}});
 map.addLayer({id:'changes',source:'land',type:'line',filter:['==',['get','iso3'],''],paint:{'line-color':'#396dbe','line-width':3,'line-dasharray':[2,1]}});
 map.addLayer({id:'selected-country',source:'land',type:'line',filter:['==',['get','iso3'],''],layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#284d64','line-width':2.2}});
 const pixels=new Uint8Array(24*24*4);for(let y=0;y<24;y++)for(let x=0;x<24;x++)pixels.set(x>=3&&x<21&&y>=3&&y<21?[36,60,73,255]:[255,255,255,255],(y*24+x)*4);map.addImage('capital-square',{width:24,height:24,data:pixels},{pixelRatio:2});
 const visible=['<=',['get','min_zoom'],['zoom']];
 map.addLayer({id:'city-dots',source:'places',type:'circle',filter:['all',['!=',['get','capital'],true],['==',['get','kind'],'city'],visible],paint:{'circle-radius':['interpolate',['linear'],['zoom'],2,1.5,7,3,11,4],'circle-color':'#243c49','circle-stroke-color':'white','circle-stroke-width':1}});
 map.addLayer({id:'capitals',source:'places',type:'symbol',filter:['all',['==',['get','capital'],true],visible],layout:{'icon-image':'capital-square','icon-size':['interpolate',['linear'],['zoom'],2,.55,7,.85,11,1],'icon-allow-overlap':true,'icon-ignore-placement':true}});
 map.addLayer({id:'city-exceptions',source:'places',type:'circle',minzoom:4,filter:['==',['get','kind'],'city_exception'],paint:{'circle-radius':5,'circle-color':palette,'circle-stroke-color':'#243c49','circle-stroke-width':1.7}});
 map.addLayer({id:'selected-city',source:'places',type:'circle',filter:['==',['get','id'],''],paint:{'circle-radius':11,'circle-color':'#315e82','circle-opacity':.13,'circle-stroke-color':'#315e82','circle-stroke-width':2}});
 map.addLayer({id:'labels',source:'places',type:'symbol',filter:visible,layout:{'text-field':['get','name'],'text-font':['Noto Sans Regular'],'text-size':['interpolate',['linear'],['zoom'],2,10,7,13,11,15],'text-variable-anchor':['left','right','top','bottom'],'text-radial-offset':.6,'text-padding':5,'symbol-sort-key':['get','priority']},paint:{'text-color':'#213946','text-halo-color':'#fff','text-halo-width':1.4}});
 const clickable=['labels','city-exceptions','capitals','city-dots','restriction-detail','detail','restriction-local','local','overview','land'];
 map.on('click',e=>{const f=map.queryRenderedFeatures(e.point,{layers:clickable})[0];if(!f)return;const p=f.properties;if(p.kind)selectCity(f).catch(fail);else choose(p.iso3,p.risk?p:null,false).catch(fail);});
 map.on('mousemove',e=>{map.getCanvas().style.cursor=map.queryRenderedFeatures(e.point,{layers:clickable}).length?'pointer':'';});
 map.on('moveend',()=>{updateHash();updateNote();viewportData();});
 $('world').onclick=()=>{reset();fitWorld();};$('clear').onclick=reset;
 $('snapshot').onchange=()=>loadSnapshot($('snapshot').value).catch(fail);$('changes').onchange=changes;
 $('fallbacks').onchange=()=>{map.setLayoutProperty('fallback','visibility',$('fallbacks').checked?'visible':'none');if(selected)choose(selected,null,false).catch(fail);};
 $('search').oninput=()=>search().catch(fail);$('search').onkeydown=e=>{if(e.key==='ArrowDown'){$('results').querySelector('button')?.focus();e.preventDefault();}if(e.key==='Escape'){$('results').hidden=true;$('search').setAttribute('aria-expanded','false');}};
 $('results').onkeydown=e=>{const buttons=[...$('results').querySelectorAll('button')],i=buttons.indexOf(document.activeElement);if(e.key==='ArrowDown'||e.key==='ArrowUp'){buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();e.preventDefault();}if(e.key==='Escape'){$('results').hidden=true;$('search').focus();}};
 document.addEventListener('click',e=>{if(!e.target.closest('.search')){$('results').hidden=true;$('search').setAttribute('aria-expanded','false');}});
 $('share').onclick=async()=>{updateHash();try{await navigator.clipboard.writeText(location.href);$('share').textContent='Link copied';notify('Map view link copied');}catch{$('share').textContent='Copy the address bar';notify('Copy the URL from the address bar to share this view');}};
 catalogue=await json('catalogue.json');$('snapshot').replaceChildren(...catalogue.snapshots.slice().reverse().map(d=>new Option(d,d)));await loadSnapshot(catalogue.snapshots.includes(initial.get('snapshot'))?initial.get('snapshot'):catalogue.current,true);
}catch(e){fail(e);}});
map.on('error',e=>fail(e.error));
