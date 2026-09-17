/* Development: faction -> site -> variant selector architecture. */
(()=>{
  const catalog={
    "Angel Cartel":{
      label:"Angel Cartel",
      sites:[
        {label:"Burrow",anomaly:"Angel Burrow"},
        {label:"Hideaway",anomaly:"Angel Hideaway"},
        {label:"Hidden Hideaway",anomaly:"Angel Hidden Hideaway"},
        {label:"Forsaken Hideaway",anomaly:"Angel Forsaken Hideaway"},
        {label:"Forlorn Hideaway",anomaly:"Angel Forlorn Hideaway"},
        {label:"Refuge",anomaly:"Angel Refuge"},
        {label:"Den",anomaly:"Angel Den"},
        {label:"Hidden Den",anomaly:"Angel Hidden Den"},
        {label:"Forsaken Den",anomaly:"Angel Forsaken Den"},
        {label:"Forlorn Den",anomaly:"Angel Forlorn Den"},
        {label:"Yard",anomaly:"Angel Yard"},
        {label:"Rally Point",anomaly:"Angel Rally Point"},
        {label:"Hidden Rally Point",anomaly:"Angel Hidden Rally Point"},
        {label:"Forsaken Rally Point",anomaly:"Angel Forsaken Rally Point"},
        {label:"Forlorn Rally Point",anomaly:"Angel Forlorn Rally Point"},
        {label:"Port",anomaly:"Angel Port"},
        {label:"Hub",anomaly:"Angel Hub"},
        {label:"Hidden Hub",anomaly:"Angel Hidden Hub"},
        {label:"Forsaken Hub",anomaly:"Angel Forsaken Hub"},
        {label:"Forlorn Hub",anomaly:"Angel Forlorn Hub"},
        {label:"Haven",anomaly:"Angel Haven"},
        {label:"Sanctum",anomaly:"Angel Sanctum"}
      ]
    }
  };
  window.SITE_CATALOG=catalog;

  const accountId=window.__BOOTSTRAP__?.account?.id||"browser";
  const factionKey=`eve-ratting:selected-faction:${accountId}`;
  const readFaction=()=>{try{return localStorage.getItem(factionKey)||""}catch{return ""}};
  const writeFaction=value=>{try{localStorage.setItem(factionKey,value)}catch{}};

  function enhanceSelector(){
    const anomaly=document.querySelector("#anomaly");
    if(!anomaly||document.querySelector("#faction"))return;
    const siteField=anomaly.closest(".field");
    if(!siteField)return;

    const supported=new Set((window.DATA?.anomalies||[]).map(String));
    const available=Object.entries(catalog)
      .map(([id,entry])=>[id,{...entry,sites:entry.sites.filter(site=>supported.has(site.anomaly))}])
      .filter(([,entry])=>entry.sites.length);
    if(!available.length)return;

    const factionField=document.createElement("div");
    factionField.className="field";
    factionField.innerHTML='<label>Faction</label><select id="faction"></select>';
    siteField.parentNode.insertBefore(factionField,siteField);
    const faction=factionField.querySelector("#faction");
    faction.innerHTML=available.map(([id,entry])=>`<option value="${id}">${entry.label}</option>`).join("");

    const siteLabel=siteField.querySelector("label");
    if(siteLabel)siteLabel.textContent="Site";
    const variant=document.querySelector("#variant");
    const variantField=variant?.closest(".field")||null;

    const remembered=readFaction();
    if(available.some(([id])=>id===remembered))faction.value=remembered;
    else faction.value=available[0][0];
    writeFaction(faction.value);

    function updateVariantVisibility(){
      if(!variantField)return;
      const variants=window.VARIANTS?.[anomaly.value]||["Default"];
      variantField.classList.toggle("hidden",variants.length<=1);
    }

    function updateSites(preserveCurrent){
      const current=preserveCurrent?anomaly.value:"";
      const entry=catalog[faction.value];
      const sites=(entry?.sites||[]).filter(site=>supported.has(site.anomaly));
      /* Keep the established anomaly text as the option label so existing
         UI automation and historical user expectations remain compatible. */
      anomaly.innerHTML=sites.map(site=>`<option value="${site.anomaly}">${site.anomaly}</option>`).join("");
      if(current&&sites.some(site=>site.anomaly===current))anomaly.value=current;
      anomaly.dispatchEvent(new Event("change",{bubbles:true}));
      updateVariantVisibility();
    }

    faction.addEventListener("change",()=>{
      writeFaction(faction.value);
      updateSites(false);
    });
    anomaly.addEventListener("change",()=>queueMicrotask(updateVariantVisibility));
    updateSites(true);
  }

  const root=document.querySelector("#trackerContent")||document.body;
  new MutationObserver(enhanceSelector).observe(root,{childList:true,subtree:true});
  enhanceSelector();
})();
