/* Topic 3: lower-tier Angel anomaly wave/trigger helpers.
   Existing Hub/Haven/Sanctum data remains untouched in site_data.js. */
(()=>{
  const V=window.VARIANTS||(window.VARIANTS={});
  const H=window.VARIANT_HINTS||(window.VARIANT_HINTS={});
  Object.assign(V,{
    "Angel Burrow":["Default"],
    "Angel Hideaway":["Default"],
    "Angel Hidden Hideaway":["Default"],
    "Angel Forsaken Hideaway":["Default"],
    "Angel Forlorn Hideaway":["Default"],
    "Angel Refuge":["Default"],
    "Angel Den":["Default"],
    "Angel Hidden Den":["Default"],
    "Angel Forsaken Den":["Default"],
    "Angel Forlorn Den":["Default"],
    "Angel Yard":["Shipyard","Silo"],
    "Angel Rally Point":["Workers Quarters","Fuel Silos"],
    "Angel Hidden Rally Point":["Default"],
    "Angel Forsaken Rally Point":["Default"],
    "Angel Forlorn Rally Point":["Default"],
    "Angel Port":["Asteroid Port","Mining Port"]
  });
  Object.assign(H,{
    "Angel Hidden Hideaway":"This site has parallel trigger branches. The helper switches between the Initial Group, Frigate branch, Cruiser branch, and Sentry chain.",
    "Angel Yard":"Choose Shipyard or Silo from the structures visible on grid. Sentry side-waves are kept separate from normal progression.",
    "Angel Rally Point":"Choose Workers Quarters or Fuel Silos from the site structures.",
    "Angel Port":"Choose Asteroid Port or Mining Port from the site layout."
  });

  const row=(icon,count,label)=>[icon,count,label,`${label} class`];
  const wave=(name,rows,note="")=>[name,rows,note];
  const lastAssumed="TRIGGER: last ship (assumed)";
  const lastShip="TRIGGER: last ship";

  const lower={
    "Angel Burrow":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","6","Frigate")],lastShip),
      wave("1st Reinforcement",[row("frigate","3–4","Frigate")],lastShip),
      wave("2nd Reinforcement",[row("frigate","2","Frigate")],lastShip),
      wave("3rd Reinforcement",[row("frigate","3","Frigate")],lastShip),
      wave("4th Reinforcement",[row("frigate","1","Frigate"),row("commander","0–1","Commander Frigate")],"Final wave")
    ]}},

    "Angel Hideaway":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","1–2","Frigate")],lastAssumed),
      wave("1st Reinforcement",[row("frigate","1–2","Frigate")],lastAssumed),
      wave("2nd Reinforcement",[row("frigate","1–3","Frigate")],lastAssumed),
      wave("3rd Reinforcement",[row("frigate","1–3","Frigate")],lastAssumed),
      wave("4th Reinforcement",[row("commander","0–1","Commander Frigate")],"Final wave · possible rare spawn")
    ]}},

    /* Rendered by site_helper_branches.js so the parallel branches are not flattened. */
    "Angel Hidden Hideaway":{variants:{"Default":[]}},

    "Angel Forsaken Hideaway":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","2–3","Frigate"),row("destroyer","2–3","Destroyer")],lastAssumed),
      wave("1st Reinforcement",[row("frigate","2–3","Elite Frigate"),row("destroyer","2","Destroyer")],lastAssumed),
      wave("2nd Reinforcement",[row("frigate","3–4","Frigate"),row("destroyer","2–3","Destroyer")],lastAssumed),
      wave("3rd Reinforcement",[row("frigate","4","Elite Frigate"),row("destroyer","4","Destroyer"),row("commander","0–1","Commander Frigate")],"Final wave · possible rare spawn")
    ]}},

    "Angel Forlorn Hideaway":{variants:{"Default":[
      wave("Initial Group",[row("frigate","5–6","Frigate")],lastAssumed),
      wave("Wave 1",[row("frigate","4","Frigate"),row("cruiser","1","Cruiser")],"TRIGGER: last Cruiser"),
      wave("Wave 2",[row("destroyer","1–2","Destroyer"),row("cruiser","3","Cruiser")],"TRIGGER: last Cruiser"),
      wave("Wave 3",[row("cruiser","5","Cruiser"),row("commander","0–1","Commander Frigate")],"Final wave · possible rare spawn")
    ]}},

    "Angel Refuge":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","2–3","Frigate"),row("sentry","2","Sentry")],lastShip),
      wave("1st Reinforcement",[row("frigate","2–3","Frigate")],lastShip),
      wave("2nd Reinforcement",[row("frigate","1–3","Frigate"),row("destroyer","0–3","Destroyer")],lastShip),
      wave("3rd Reinforcement",[row("frigate","0–3","Frigate"),row("destroyer","1–3","Destroyer")],lastShip),
      wave("4th Reinforcement",[row("frigate","0–3","Frigate"),row("destroyer","1–2","Destroyer")],lastShip),
      wave("Optional Commander",[row("commander","0–1","Commander Destroyer")],"Possible rare spawn")
    ]}},

    "Angel Den":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","6","Frigate"),row("destroyer","2","Destroyer"),row("sentry","2","Sentry")],lastAssumed),
      wave("1st Reinforcement",[row("destroyer","2","Destroyer"),row("cruiser","2","Cruiser")],lastAssumed),
      wave("2nd Reinforcement",[row("frigate","2","Frigate"),row("cruiser","2","Cruiser")],lastAssumed),
      wave("3rd Reinforcement",[row("destroyer","2","Destroyer"),row("cruiser","3","Cruiser")],lastAssumed),
      wave("4th Reinforcement",[row("destroyer","5","Destroyer"),row("cruiser","5","Cruiser"),row("commander","0–1","Commander Cruiser")],"Final wave · possible rare spawn")
    ]}},

    "Angel Hidden Den":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","8","Frigate"),row("destroyer","11","Destroyer"),row("cruiser","5","Cruiser"),row("battlecruiser","3","Battlecruiser"),row("sentry","1","Sentry")],lastAssumed),
      wave("1st Reinforcement",[row("frigate","3","Frigate"),row("cruiser","3","Cruiser")],lastAssumed),
      wave("2nd Reinforcement",[row("frigate","4","Frigate"),row("destroyer","3","Destroyer")],lastAssumed),
      wave("3rd Reinforcement",[row("frigate","2","Frigate"),row("destroyer","3","Destroyer")],lastAssumed),
      wave("4th Reinforcement",[row("frigate","3","Frigate"),row("cruiser","2","Cruiser"),row("battlecruiser","3","Battlecruiser")],"TRIGGER: last Battlecruiser"),
      wave("5th Reinforcement",[row("frigate","6","Frigate"),row("battlecruiser","5","Battlecruiser"),row("battleship","2","Battleship")],"TRIGGER: last Battlecruiser"),
      wave("6th Reinforcement",[row("frigate","4","Frigate"),row("cruiser","2","Cruiser")],lastAssumed),
      wave("7th Reinforcement",[row("frigate","2","Elite Frigate"),row("cruiser","2","Cruiser"),row("battlecruiser","5","Battlecruiser")],"TRIGGER: last Frigate"),
      wave("8th Reinforcement",[row("frigate","2","Frigate"),row("cruiser","3","Cruiser"),row("battlecruiser","3","Battlecruiser")],lastAssumed),
      wave("9th Reinforcement",[row("frigate","3","Elite Frigate"),row("cruiser","4","Cruiser"),row("battlecruiser","7","Battlecruiser")],"Final wave")
    ]}},

    "Angel Forsaken Den":{variants:{"Default":[
      wave("Initial Defenders",[row("cruiser","2–3","Elite Cruiser"),row("battlecruiser","3","Battlecruiser")],lastAssumed),
      wave("1st Reinforcement",[row("frigate","2–3","Elite Frigate"),row("cruiser","3","Elite Cruiser")],lastAssumed),
      wave("2nd Reinforcement",[row("cruiser","3","Elite Cruiser"),row("battlecruiser","3–4","Battlecruiser")],lastAssumed),
      wave("3rd Reinforcement",[row("battlecruiser","3–4","Battlecruiser")],lastAssumed),
      wave("4th Reinforcement",[row("cruiser","4","Cruiser"),row("battlecruiser","3–4","Battlecruiser")],lastAssumed),
      wave("5th Reinforcement",[row("frigate","2–3","Elite Frigate"),row("battlecruiser","2–3","Battlecruiser")],"Final wave")
    ]}},

    "Angel Forlorn Den":{variants:{"Default":[
      wave("Initial Defenders",[row("frigate","6","Elite Frigate")],lastAssumed),
      wave("1st Reinforcement",[row("frigate","6","Elite Frigate"),row("cruiser","5","Cruiser"),row("battleship","2","Battleship")],"TRIGGER: last Frigate"),
      wave("2nd Reinforcement",[row("destroyer","5","Destroyer"),row("cruiser","4","Cruiser"),row("battleship","2","Battleship")],"TRIGGER: last Cruiser"),
      wave("3rd Reinforcement",[row("cruiser","5","Cruiser"),row("battlecruiser","6","Battlecruiser"),row("battleship","2","Battleship")],"TRIGGER: last Battlecruiser"),
      wave("4th Reinforcement",[row("battlecruiser","10","Battlecruiser")],"TRIGGER: one random Battlecruiser"),
      wave("5th Reinforcement",[row("frigate","3","Elite Frigate"),row("cruiser","3","Elite Cruiser"),row("battleship","4","Battleship")],"Final wave")
    ]}},

    "Angel Yard":{variants:{
      "Shipyard":[
        wave("Initial Group",[row("sentry","2","Sentry"),row("cruiser","3–4","Cruiser")],lastAssumed),
        wave("Sentry Side Wave",[row("destroyer","2–3","Destroyer"),row("cruiser","2–3","Cruiser")],"Side wave from sentries · trigger not confirmed"),
        wave("Wave 2",[row("cruiser","3–4","Cruiser")],lastAssumed),
        wave("Wave 3",[row("frigate","3","Frigate"),row("cruiser","2–3","Cruiser")],lastAssumed),
        wave("Wave 4",[row("destroyer","3–4","Destroyer"),row("cruiser","3–4","Cruiser")],"Final normal wave")
      ],
      "Silo":[
        wave("Initial Group",[row("destroyer","3","Destroyer"),row("cruiser","3–4","Cruiser")],lastAssumed),
        wave("Wave 2",[row("sentry","2","Sentry"),row("cruiser","3–4","Cruiser"),row("battlecruiser","2","Battlecruiser")],lastAssumed),
        wave("Sentry Side Wave",[row("sentry","2","Sentry")],"Separate sentry side-wave · trigger not confirmed"),
        wave("Wave 3",[row("frigate","2–3","Elite Frigate"),row("cruiser","2–3","Cruiser")],lastAssumed),
        wave("Wave 4",[row("cruiser","1–3","Cruiser")],lastAssumed),
        wave("Wave 5",[row("cruiser","1","Cruiser"),row("battleship","1","Battleship")],"Final normal wave")
      ]
    }},

    "Angel Rally Point":{variants:{
      "Workers Quarters":[
        wave("Initial Defenders",[row("destroyer","3–4","Destroyer"),row("cruiser","3–4","Cruiser"),row("sentry","2","Sentry")],lastShip),
        wave("1st Reinforcement",[row("frigate","2–3","Elite Frigate"),row("cruiser","2–3","Cruiser")],lastShip),
        wave("2nd Reinforcement",[row("frigate","1–2","Elite Frigate"),row("battlecruiser","3–4","Battlecruiser")],lastShip),
        wave("3rd Reinforcement",[row("cruiser","3–4","Cruiser"),row("battlecruiser","3–4","Battlecruiser")],lastShip),
        wave("4th Reinforcement",[row("battlecruiser","1–2","Battlecruiser"),row("battleship","1–2","Battleship"),row("commander","0–1","Commander Battlecruiser")],"Final wave · possible rare spawn")
      ],
      "Fuel Silos":[
        wave("Initial Defenders",[row("frigate","3–4","Frigate"),row("destroyer","4","Destroyer"),row("sentry","4","Sentry")],lastShip),
        wave("1st Reinforcement",[row("frigate","2–3","Frigate"),row("cruiser","2–3","Cruiser")],lastShip),
        wave("2nd Reinforcement",[row("frigate","2–3","Elite Frigate"),row("cruiser","2–3","Cruiser")],lastShip),
        wave("3rd Reinforcement",[row("frigate","2–3","Frigate"),row("battlecruiser","2–3","Battlecruiser")],lastShip),
        wave("4th Reinforcement",[row("frigate","1–2","Elite Frigate"),row("battlecruiser","1–2","Battlecruiser")],lastShip),
        wave("5th Reinforcement",[row("battlecruiser","3–4","Battlecruiser")],lastShip),
        wave("6th Reinforcement",[row("cruiser","2–3","Elite Cruiser"),row("battlecruiser","2–3","Battlecruiser")],lastShip),
        wave("7th Reinforcement",[row("battlecruiser","1–2","Battlecruiser"),row("battleship","1–2","Battleship"),row("commander","0–1","Commander Battlecruiser")],"Final wave · possible rare spawn")
      ]
    }},

    "Angel Hidden Rally Point":{variants:{"Default":[
      wave("Initial Defenders",[row("destroyer","5","Destroyer"),row("cruiser","6","Cruiser"),row("battlecruiser","3","Battlecruiser"),row("battleship","3","Battleship")],"TRIGGER: last Cruiser"),
      wave("1st Reinforcement",[row("frigate","3","Elite Frigate"),row("cruiser","6","Cruiser"),row("battlecruiser","9","Battlecruiser"),row("battleship","4","Battleship")],"TRIGGER: last Cruiser or Battlecruiser, whichever class finishes last"),
      wave("2nd Reinforcement",[row("cruiser","7","Cruiser"),row("battlecruiser","7","Battlecruiser")],"TRIGGER: last Battlecruiser"),
      wave("3rd Reinforcement",[row("frigate","2","Elite Frigate"),row("cruiser","5","Cruiser"),row("battlecruiser","6","Battlecruiser"),row("battleship","2","Battleship")],"TRIGGER: last Elite Cruiser"),
      wave("4th Reinforcement",[row("cruiser","3","Elite Cruiser"),row("battleship","8","Battleship")],"Final wave")
    ]}},

    "Angel Forsaken Rally Point":{variants:{"Default":[
      wave("Initial Defenders",[row("cruiser","1–2","Elite Cruiser"),row("battleship","1–2","Battleship")],"TRIGGER: final kill of the wave"),
      wave("1st Reinforcement",[row("frigate","2–3","Elite Frigate"),row("battleship","2–3","Battleship")],"TRIGGER: final kill of the wave"),
      wave("2nd Reinforcement",[row("cruiser","2–3","Cruiser"),row("battleship","2–3","Battleship")],"TRIGGER: final kill of the wave"),
      wave("3rd Reinforcement",[row("frigate","2–3","Elite Frigate"),row("battleship","3","Battleship")],"TRIGGER: final kill of the wave"),
      wave("4th Reinforcement",[row("battlecruiser","3–4","Battlecruiser"),row("battleship","3–4","Battleship")],"TRIGGER: final kill of the wave"),
      wave("5th Reinforcement",[row("cruiser","3–4","Elite Cruiser"),row("battleship","3","Battleship")],"TRIGGER: final kill of the wave"),
      wave("6th Reinforcement",[row("battleship","3–4","Battleship")],"Final wave")
    ]}},

    "Angel Forlorn Rally Point":{variants:{"Default":[
      wave("Initial Defenders",[row("destroyer","6","Destroyer"),row("cruiser","4","Cruiser")],lastShip),
      wave("1st Reinforcement",[row("cruiser","4","Cruiser"),row("battlecruiser","5","Battlecruiser"),row("battleship","4","Battleship")],lastShip),
      wave("2nd Reinforcement",[row("cruiser","4","Cruiser"),row("battlecruiser","5","Battlecruiser"),row("battleship","3","Battleship")],lastShip),
      wave("3rd Reinforcement",[row("cruiser","4","Elite Cruiser"),row("battlecruiser","6","Battlecruiser"),row("battleship","4","Battleship")],lastShip),
      wave("4th Reinforcement",[row("cruiser","4","Elite Cruiser"),row("battleship","4","Battleship"),row("commander","0–1","Commander Cruiser")],"Final wave · possible rare spawn")
    ]}},

    "Angel Port":{variants:{
      "Asteroid Port":[
        wave("Initial Defenders",[row("frigate","3–4","Elite Frigate"),row("battlecruiser","3–4","Battlecruiser"),row("sentry","4","Sentry")],"TRIGGER: last Battlecruiser"),
        wave("1st Reinforcement",[row("frigate","2–3","Elite Frigate"),row("battlecruiser","2–3","Battlecruiser")],"TRIGGER: last Battlecruiser"),
        wave("2nd Reinforcement",[row("destroyer","3–4","Destroyer"),row("battlecruiser","6–7","Battlecruiser"),row("battleship","0–4","Battleship")],"TRIGGER: last Battleship"),
        wave("3rd Reinforcement",[row("battlecruiser","3–4","Battlecruiser"),row("battleship","2–4","Battleship"),row("commander","0–1","Commander Battleship")],"Final wave · possible rare spawn")
      ],
      "Mining Port":[
        wave("Initial Defenders",[row("destroyer","3","Destroyer"),row("cruiser","3–4","Cruiser"),row("sentry","4","Sentry")],"TRIGGER: last non-sentry ship"),
        wave("1st Reinforcement",[row("destroyer","3–4","Destroyer"),row("battlecruiser","3–4","Battlecruiser")],lastAssumed),
        wave("2nd Reinforcement",[row("cruiser","3","Cruiser"),row("battleship","2–3","Battleship")],lastAssumed),
        wave("3rd Reinforcement",[row("battlecruiser","3–4","Battlecruiser"),row("battleship","3–4","Battleship")],"Final wave")
      ]
    }}
  };

  Object.assign(window.SITE_DATA||(window.SITE_DATA={}),lower);

  window.HIDDEN_HIDEAWAY_BRANCHES={
    initial:{
      title:"Initial Group",
      rows:[row("sentry","1","Sentry"),row("frigate","5–6","Frigate"),row("cruiser","1–2","Cruiser")],
      choices:[
        {id:"frigate",label:"Frigate branch · Wave 2a",trigger:"Clear all Frigates"},
        {id:"cruiser",label:"Cruiser branch · Wave 2b",trigger:"Clear all Cruisers"},
        {id:"sentry",label:"Sentry chain",trigger:"Destroy the Sentry"}
      ]
    },
    branches:{
      frigate:{label:"Frigate branch · Wave 2a",waves:[
        wave("Wave 2a",[row("destroyer","2–3","Destroyer")],"Branch spawn · no further trigger confirmed")
      ]},
      cruiser:{label:"Cruiser branch · Wave 2b",waves:[
        wave("Wave 2b",[row("frigate","3–4","Frigate"),row("destroyer","3–4","Destroyer")],"Branch spawn · no further trigger confirmed")
      ]},
      sentry:{label:"Sentry chain",waves:[
        wave("Sentry Wave 1",[row("frigate","3–4","Frigate"),row("cruiser","1–2","Cruiser")],"TRIGGER: last Cruiser"),
        wave("Sentry Wave 2",[row("frigate","3–4","Frigate"),row("destroyer","1–2","Destroyer")],"TRIGGER: last Destroyer"),
        wave("Sentry Wave 3",[row("frigate","3–5","Frigate"),row("cruiser","1–2","Cruiser"),row("commander","0–1","Commander Frigate")],"TRIGGER: last Frigate")
      ]}
    }
  };
})();
