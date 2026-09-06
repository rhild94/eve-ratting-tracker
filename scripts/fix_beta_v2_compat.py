from pathlib import Path
p=Path('static/beta_features_v2.js')
s=p.read_text(encoding='utf-8')
s=s.replace('class="beta-fit-select-v2"','class="beta-fit-select beta-fit-select-v2"')
s=s.replace('id="v2AddFit"','id="betaAddFit"')
s=s.replace("q('#v2AddFit',root)","q('#betaAddFit',root)")
compat='''\nwindow.renderEsiStatus=window.renderEsiStatus||function(){\n const e=(window.DATA&&window.DATA.esi)||{},pending=Number(e.pending_runs||0),status=document.querySelector('#systemStatus'),alertBox=document.querySelector('#esiAlert');\n const parts=[e.last_success||e.last_sync?'Synced recently':'Not synced yet',e.next_check?'Next check scheduled':'Auto sync enabled',pending+' run'+(pending===1?'':'s')+' pending bounty data'];\n if(status)status.textContent='ESI: '+parts.join(' · ');\n if(alertBox){if(e.last_error){alertBox.textContent='⚠ ESI sync issue — ESI-based values may be stale. Local tracker data is safe.';alertBox.title=e.last_error;alertBox.classList.remove('hidden')}else{alertBox.textContent='';alertBox.title='';alertBox.classList.add('hidden')}}\n};\n'''
if 'window.renderEsiStatus=window.renderEsiStatus||function' not in s:s+=compat
p.write_text(s,encoding='utf-8')
print('Beta v2 compatibility layer applied.')
