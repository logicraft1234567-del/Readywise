(function(){var t;try{t=localStorage.getItem("rw-theme")}catch(e){}if(!t)t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t})();
function rwChartTheme(){if(!window.Chart)return;var d=document.documentElement.dataset.theme==="dark";Chart.defaults.color=d?"#97A3BF":"#5C687E";Chart.defaults.borderColor=d?"#222C46":"#E2E5EC";Chart.defaults.font.family="Geist, system-ui, sans-serif"}
rwChartTheme();
function toggleTheme(){var n=document.documentElement.dataset.theme==="dark"?"light":"dark";try{localStorage.setItem("rw-theme",n)}catch(e){}document.documentElement.dataset.theme=n;if(document.querySelector("canvas"))location.reload()}
function rwBrand(){return getComputedStyle(document.documentElement).getPropertyValue("--b1").trim()||"#2B44E8"}
