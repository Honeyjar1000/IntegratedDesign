
async function postJSON(url, body){
  const res = await fetch(url, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body||{}) });
  return res.json();
}
function updateStatus(j){
  const el = document.getElementById("status");
  if(!el) return;
  if(j && j.ok){
    const L = j.left || {dir:0,duty:0}, R = j.right || {dir:0,duty:0};
    const fmt = x => (typeof x==="number" ? x.toFixed(2) : x);
    el.textContent = `L: dir ${L.dir} duty ${fmt(L.duty)} | R: dir ${R.dir} duty ${fmt(R.duty)}`;
  } else if(j && j.error){
    el.textContent = `error: ${j.error}`;
  }
}
async function drive(left, right){ updateStatus(await postJSON("/drive", {left, right})); }
async function stop(){ updateStatus(await postJSON("/stop", {})); }

document.getElementById("btnFwd").addEventListener("click", ()=>drive(1, 1));
document.getElementById("btnRev").addEventListener("click", ()=>drive(-1, -1));
document.getElementById("btnL").addEventListener("click", ()=>drive(-1, 1));
document.getElementById("btnR").addEventListener("click", ()=>drive(1, -1));
document.getElementById("btnStop").addEventListener("click", stop);

// Keyboard: send once on keydown, stop on keyup
const pressed = new Set();
window.addEventListener("keydown", (e)=>{
  if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.code)) e.preventDefault();
  if(pressed.has(e.code)) return;  // ignore auto-repeat
  pressed.add(e.code);
  if(e.code==="ArrowUp") drive(1, 1);
  if(e.code==="ArrowDown") drive(-1, -1);
  if(e.code==="ArrowLeft") drive(-1, 1);
  if(e.code==="ArrowRight") drive(1, -1);
});
window.addEventListener("keyup", (e)=>{
  if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.code)) e.preventDefault();
  pressed.delete(e.code);
  // if no arrow keys are held, stop
  const anyHeld = ["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].some(k => pressed.has(k));
  if(!anyHeld) stop();
});

// Optional: periodic status
setInterval(async ()=>{
  try{
    const r = await fetch("/status"); updateStatus(await r.json());
  }catch{}
}, 3000);