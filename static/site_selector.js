/* Tracker site picker: account-scoped favorites + wiki-style anomaly tiers. */
(()=>{
  'use strict';

  const catalog={
    "Angel Cartel":{
      label:"Angel Cartel",
      sites:[
        {label:"Hideaway",anomaly:"Angel Hideaway",tier:1,level:1,found:"High / Low"},
        {label:"Hidden Hideaway",anomaly:"Angel Hidden Hideaway",tier:1,level:2,found:"High / Low"},
        {label:"Forsaken Hideaway",anomaly:"Angel Forsaken Hideaway",tier:1,level:3,found:"High / Low"},
        {label:"Forlorn Hideaway",anomaly:"Angel Forlorn Hideaway",tier:1,level:4,found:"High / Low"},
        {label:"Burrow",anomaly:"Angel Burrow",tier:2,level:null,found:"High"},
        {label:"Refuge",anomaly:"Angel Refuge",tier:3,level:null,found:"High / Low"},
        {label:"Den",anomaly:"Angel Den",tier:4,level:1,found:"High / Low"},
        {label:"Hidden Den",anomaly:"Angel Hidden Den",tier:4,level:2,found:"Low / Null"},
        {label:"Forsaken Den",anomaly:"Angel Forsaken Den",tier:4,level:3,found:"Low / Null"},
        {label:"Forlorn Den",anomaly:"Angel Forlorn Den",tier:4,level:4,found:"Low / Null"},
        {label:"Yard",anomaly:"Angel Yard",tier:5,level:null,found:"Low"},
        {label:"Rally Point",anomaly:"Angel Rally Point",tier:6,level:1,found:"Low / Null"},
        {label:"Hidden Rally Point",anomaly:"Angel Hidden Rally Point",tier:6,level:2,found:"Low / Null"},
        {label:"Forsaken Rally Point",anomaly:"Angel Forsaken Rally Point",tier:6,level:3,found:"Low / Null"},
        {label:"Forlorn Rally Point",anomaly:"Angel Forlorn Rally Point",tier:6,level:4,found:"Low / Null"},
        {label:"Port",anomaly:"Angel Port",tier:7,level:null,found:"Low / Null"},
        {label:"Hub",anomaly:"Angel Hub",tier:8,level:1,found:"Low / Null"},
        {label:"Hidden Hub",anomaly:"Angel Hidden Hub",tier:8,level:2,found:"Low / Null"},
        {label:"Forsaken Hub",anomaly:"Angel Forsaken Hub",tier:8,level:3,found:"Low / Null"},
        {label:"Forlorn Hub",anomaly:"Angel Forlorn Hub",tier:8,level:4,found:"Low / Null"},
        {label:"Haven",anomaly:"Angel Haven",tier:9,level:null,found:"Null"},
        {label:"Sanctum",anomaly:"Angel Sanctum",tier:10,level:1,found:"Null"}
      ]
    }
  };

  const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
  const allSites=Object.entries(catalog).flatMap(([faction,entry])=>entry.sites.map(site=>({...site,faction,label:site.label||site.anomaly})));
  const byAnomaly=new Map(allSites.map(site=>[site.anomaly,site]));
  const accountId=window.__BOOTSTRAP__?.account?.id||"browser";
  const selectedKey=`eve-ratting:selected-site:${accountId}`;
  let pickerSelection=null;
  let searchQuery="";

  window.SITE_CATALOG=catalog;
  window.SITE_META=Object.fromEntries(allSites.map(site=>[site.anomaly,{...site}]));

  const data=()=>window.DATA||window.INITIAL_DATA||{};
  const supported=()=>new Set((data().anomalies||[]).map(String));
  const availableSites=()=>allSites.filter(site=>supported().has(site.anomaly));
  const favorites=()=>new Set((data().favorite_sites||[]).filter(x=>supported().has(x)));

  function rating(site){
    if(!site)return "";
    return `Tier ${site.tier}${site.level?` · Level ${site.level}`:""}`;
  }
  function variants(site){
    const list=window.VARIANTS?.[site?.anomaly]||["Default"];
    return list;
  }
  function readSelected(){
    let local="";
    try{local=localStorage.getItem(selectedKey)||""}catch{}
    const supportedNow=supported();
    if(local&&supportedNow.has(local))return local;
    const server=data().last_site;
    if(server&&supportedNow.has(server))return server;
    return availableSites()[0]?.anomaly||"";
  }
  function rememberSelected(anomaly){
    try{localStorage.setItem(selectedKey,anomaly)}catch{}
  }
  function nativeSelect(){
    return document.querySelector("#anomaly");
  }
  function currentSite(){
    return byAnomaly.get(nativeSelect()?.value||readSelected())||availableSites()[0]||null;
  }
  function setNative(anomaly){
    const select=nativeSelect();
    if(!select||!supported().has(anomaly))return;
    select.value=anomaly;
    rememberSelected(anomaly);
    select.dispatchEvent(new Event("change",{bubbles:true}));
    renderMainSelection();
  }

  function favoriteButton(site,isFavorite,extra=""){
    return `<button type="button" class="site-star ${isFavorite?"is-favorite":""} ${extra}" data-favorite-site="${esc(site.anomaly)}" aria-label="${isFavorite?"Remove from":"Add to"} favorites" title="${isFavorite?"Remove from":"Add to"} favorites">${isFavorite?"★":"☆"}</button>`;
  }

  function renderQuickFavorites(){
    const host=document.querySelector("#siteQuickFavorites");
    if(!host)return;
    const fav=favorites();
    const sites=availableSites().filter(site=>fav.has(site.anomaly));
    if(!sites.length){
      host.innerHTML='<span class="site-favorites-empty">No favorites yet · star sites in Change Site for quick access.</span>';
      return;
    }
    host.innerHTML=sites.map(site=>`<button type="button" class="site-favorite-chip ${nativeSelect()?.value===site.anomaly?"selected":""}" data-quick-site="${esc(site.anomaly)}"><span>★</span>${esc(site.anomaly)}<small>${esc(rating(site))}</small></button>`).join("");
    host.querySelectorAll("[data-quick-site]").forEach(btn=>btn.addEventListener("click",()=>setNative(btn.dataset.quickSite)));
  }

  function renderMainSelection(){
    const site=currentSite();
    if(!site)return;
    const fav=favorites().has(site.anomaly);
    const name=document.querySelector("#selectedSiteName");
    const meta=document.querySelector("#selectedSiteRating");
    const star=document.querySelector("#selectedSiteFavorite");
    if(name)name.textContent=site.anomaly;
    if(meta)meta.textContent=rating(site);
    if(star){
      star.textContent=fav?"★":"☆";
      star.classList.toggle("is-favorite",fav);
      star.dataset.favoriteSite=site.anomaly;
      star.title=fav?"Remove from favorites":"Add to favorites";
    }
    renderQuickFavorites();
  }

  async function toggleFavorite(anomaly){
    if(!supported().has(anomaly))return;
    const before=[...(data().favorite_sites||[])];
    const set=new Set(before);
    const adding=!set.has(anomaly);
    if(adding)set.add(anomaly);else set.delete(anomaly);
    data().favorite_sites=[...set];
    renderMainSelection();
    if(document.querySelector(".site-picker-modal"))renderPickerLists();
    try{
      const r=await fetch("/api/preferences/favorite-site",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({anomaly,favorite:adding})});
      const j=await r.json();
      if(!r.ok)throw new Error(j.error||"Could not save favorite.");
      data().favorite_sites=j.favorite_sites||[];
      renderMainSelection();
      if(document.querySelector(".site-picker-modal"))renderPickerLists();
    }catch(err){
      data().favorite_sites=before;
      renderMainSelection();
      if(document.querySelector(".site-picker-modal"))renderPickerLists();
      alert(err.message||"Could not save favorite.");
    }
  }

  function wireFavoriteButtons(root=document){
    root.querySelectorAll?.("[data-favorite-site]").forEach(btn=>{
      if(btn.dataset.favoriteBound)return;
      btn.dataset.favoriteBound="1";
      btn.addEventListener("click",e=>{e.stopPropagation();toggleFavorite(btn.dataset.favoriteSite)});
    });
  }

  function siteCard(site,{favoriteSection=false}={}){
    const isFav=favorites().has(site.anomaly);
    const selected=pickerSelection===site.anomaly;
    return `<article class="site-picker-card ${selected?"selected":""} ${favoriteSection?"favorite-card":""}" data-picker-site="${esc(site.anomaly)}">
      ${favoriteButton(site,isFav)}
      <strong>${esc(site.anomaly)}</strong>
      <span class="site-rating-badge">${esc(rating(site))}</span>
      <small>${esc(site.found)} sec</small>
    </article>`;
  }

  function filteredSites(){
    const q=searchQuery.trim().toLowerCase();
    return availableSites().filter(site=>!q||`${site.anomaly} ${site.faction} tier ${site.tier} level ${site.level||""}`.toLowerCase().includes(q));
  }

  function listsMarkup(){
    const all=filteredSites(), fav=favorites();
    const favoriteSites=all.filter(site=>fav.has(site.anomaly));
    const tiers=[...new Set(all.map(site=>site.tier))].sort((a,b)=>a-b);
    let out='<section class="site-picker-section favorites-section"><div class="site-picker-section-head"><h3>★ Favorites</h3><span>'+favoriteSites.length+'</span></div>';
    out+=favoriteSites.length?`<div class="site-picker-grid">${favoriteSites.map(site=>siteCard(site,{favoriteSection:true})).join("")}</div>`:'<p class="site-picker-empty">Star the sites you run most often and they will stay here.</p>';
    out+='</section>';
    for(const tier of tiers){
      const sites=all.filter(site=>site.tier===tier);
      if(!sites.length)continue;
      out+=`<section class="site-picker-section"><div class="site-picker-section-head"><h3>Tier ${tier}</h3><span>${sites.length}</span></div><div class="site-picker-grid">${sites.map(site=>siteCard(site)).join("")}</div></section>`;
    }
    if(!all.length)out+='<div class="site-picker-empty large">No sites match your search.</div>';
    return out;
  }

  function detailMarkup(){
    const site=byAnomaly.get(pickerSelection)||availableSites()[0];
    if(!site)return '<div class="site-picker-empty large">No supported sites.</div>';
    const fav=favorites().has(site.anomaly);
    const variantList=variants(site);
    return `<div class="site-picker-detail-art" role="img" aria-label="EVE space artwork"></div>
      <div class="site-picker-detail-title">${favoriteButton(site,fav,"detail-star")}<div><span class="small-title">Selected Site</span><h2>${esc(site.anomaly)}</h2></div></div>
      <div class="site-rating-badge prominent">${esc(rating(site))}</div>
      <p class="site-picker-detail-copy">Choose the site here, then pick its variant on the Tracker before starting.</p>
      <dl class="site-picker-facts">
        <div><dt>Faction</dt><dd>${esc(catalog[site.faction]?.label||site.faction)}</dd></div>
        <div><dt>Found in</dt><dd>${esc(site.found)} sec</dd></div>
        <div><dt>Tier</dt><dd>${site.tier}</dd></div>
        <div><dt>Level</dt><dd>${site.level||"Base"}</dd></div>
        <div class="full"><dt>Variants</dt><dd>${esc(variantList.join(", "))}</dd></div>
      </dl>
      <div class="site-picker-detail-actions">
        <button type="button" id="useSelectedSite" class="site-use-button big">▶ Use ${esc(site.anomaly)}</button>
        <button type="button" id="cancelSitePicker" class="secondary">Cancel</button>
      </div>`;
  }

  function wirePicker(){
    const modal=document.querySelector("#modalContent");
    if(!modal)return;
    modal.querySelectorAll("[data-picker-site]").forEach(card=>card.addEventListener("click",e=>{
      if(e.target.closest("[data-favorite-site]"))return;
      pickerSelection=card.dataset.pickerSite;
      renderPickerLists();
    }));
    wireFavoriteButtons(modal);
    modal.querySelector("#useSelectedSite")?.addEventListener("click",()=>{
      if(pickerSelection)setNative(pickerSelection);
      closePicker();
    });
    modal.querySelector("#cancelSitePicker")?.addEventListener("click",closePicker);
  }

  function renderPickerLists(){
    const list=document.querySelector("#sitePickerList");
    const detail=document.querySelector("#sitePickerDetail");
    if(list)list.innerHTML=listsMarkup();
    if(detail)detail.innerHTML=detailMarkup();
    wirePicker();
  }

  function openPicker(){
    const select=nativeSelect();
    if(!select)return;
    pickerSelection=select.value||readSelected();
    searchQuery="";
    const modal=document.querySelector("#modalContent"),backdrop=document.querySelector("#modalBackdrop");
    if(!modal||!backdrop)return;
    modal.className="modal site-picker-modal";
    modal.innerHTML=`<div class="modal-head site-picker-head"><div><span class="eyebrow">SITE CATALOG</span><h2>Choose Site</h2><p class="hint">Quickly select the anomaly you want to run. Favorites stay at the top.</p></div><button id="closeSitePicker" class="icon-btn" aria-label="Close">×</button></div>
      <div class="site-picker-toolbar"><span class="site-search-icon">⌕</span><input id="siteSearch" autocomplete="off" placeholder="Search sites..." aria-label="Search sites"><button type="button" id="clearSiteSearch" class="tiny secondary">Clear</button><span class="site-faction-pill">Angel Cartel</span></div>
      <div class="site-picker-layout"><div id="sitePickerList" class="site-picker-list"></div><aside id="sitePickerDetail" class="site-picker-detail"></aside></div>`;
    backdrop.classList.remove("hidden");
    modal.querySelector("#closeSitePicker").onclick=closePicker;
    const input=modal.querySelector("#siteSearch");
    input.addEventListener("input",()=>{searchQuery=input.value;renderPickerLists()});
    modal.querySelector("#clearSiteSearch").onclick=()=>{searchQuery="";input.value="";renderPickerLists();input.focus()};
    renderPickerLists();
    setTimeout(()=>input.focus(),0);
  }

  function closePicker(){
    const modal=document.querySelector("#modalContent"),backdrop=document.querySelector("#modalBackdrop");
    if(modal)modal.className="modal";
    if(backdrop)backdrop.classList.add("hidden");
  }

  function enhanceSelector(){
    const anomaly=nativeSelect();
    if(!anomaly||anomaly.dataset.sitePickerEnhanced)return;
    const field=anomaly.closest(".field");
    if(!field)return;
    anomaly.dataset.sitePickerEnhanced="1";
    field.classList.add("site-native-field");

    const selected=readSelected();
    if(selected&&supported().has(selected))anomaly.value=selected;
    rememberSelected(anomaly.value);

    const block=document.createElement("div");
    block.className="field full site-choice-block";
    block.innerHTML=`<label>Site</label>
      <div class="site-choice-card">
        <div class="site-choice-copy"><span class="small-title">Selected Site</span><h3 id="selectedSiteName"></h3><span id="selectedSiteRating" class="site-rating-badge"></span></div>
        <div class="site-choice-actions"><button type="button" id="selectedSiteFavorite" class="site-star large-star" aria-label="Toggle favorite"></button><button type="button" id="changeSite" class="secondary big">Change Site</button></div>
      </div>
      <div class="site-quick-wrap"><span class="small-title">Favorites</span><div id="siteQuickFavorites" class="site-quick-favorites"></div></div>`;
    field.parentNode.insertBefore(block,field);
    block.querySelector("#changeSite").addEventListener("click",openPicker);
    block.querySelector("#selectedSiteFavorite").addEventListener("click",e=>{e.stopPropagation();toggleFavorite(e.currentTarget.dataset.favoriteSite)});
    anomaly.addEventListener("change",()=>renderMainSelection());
    renderMainSelection();
  }

  const root=document.querySelector("#trackerContent")||document.body;
  new MutationObserver(enhanceSelector).observe(root,{childList:true,subtree:true});
  document.addEventListener("click",e=>{
    if(e.target?.id==="modalBackdrop"&&document.querySelector("#modalContent.site-picker-modal"))closePicker();
  },true);
  window.SITE_PICKER={open:openPicker,close:closePicker,refresh:renderMainSelection,toggleFavorite};
  enhanceSelector();
})();