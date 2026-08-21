var o=Object.defineProperty;var s=(r,e,t)=>e in r?o(r,e,{enumerable:!0,configurable:!0,writable:!0,value:t}):r[e]=t;var i=(r,e,t)=>s(r,typeof e!="symbol"?e+"":e,t);import{R as c,a as l}from"./routeState.CqTERXm9.js";const a={prepare:{title:"Подготовка",desc:"Выбор профилей оборудования, калибровки, параметров входа CH1/CH2."},capture:{title:"Захват",desc:"Запуск одиночных или серийных измерений, отображение активной задачи."},inspect:{title:"Инспекция",desc:"Детальный анализ выбранной сессии, просмотр спектра мощности (PSD)."},experiments:{title:"Эксперименты",desc:"Группировка сессий по протоколам (A/B, A/B/A, повторные серии)."},reports:{title:"Отчёты",desc:"Генерация научных отчетов с полной прослеживаемостью (provenance)."},settings:{title:"Настройки",desc:"Управление путями сессий, базами данных, резервным копированием."}};class d{constructor(e){i(this,"container");i(this,"currentRoute","prepare");i(this,"routes");this.container=e,this.routes=new c(window),window.addEventListener("hashchange",()=>this.handleRoute())}init(){try{this.renderShell(),this.handleRoute()}catch(e){this.renderErrorBoundary(e)}}renderShell(){this.container.innerHTML=`
      <header class="app-header">
        <h1 class="app-title">LNT v2</h1>
        <nav class="app-nav" role="navigation">
          ${Object.entries(a).map(([e,t])=>`
            <a href="#/${e}" class="nav-link" id="nav-${e}" data-route="${e}">${t.title}</a>
          `).join("")}
        </nav>
      </header>
      <main class="app-main" id="app-main">
        <div class="view-container" id="view-container"></div>
      </main>
    `}handleRoute(){try{if(!window.location.hash.startsWith("#/")){window.location.hash="#/prepare";return}this.routes.syncFromUrl();const t=this.routes.get(),n=t.route in a?t.route:"prepare";n!==this.currentRoute&&l(`Раздел: ${a[n].title}`),this.currentRoute=n,this.updateActiveNav(),this.renderView()}catch(e){this.renderErrorBoundary(e)}}updateActiveNav(){const e=this.container.querySelectorAll(".nav-link");for(const t of e)t.getAttribute("data-route")===this.currentRoute?t.classList.add("active"):t.classList.remove("active")}renderView(){const e=this.container.querySelector("#view-container");if(!e)return;if(this.currentRoute==="experiments"&&window.location.search.includes("trigger-error"))throw new Error("Тестовая критическая ошибка в представлении Эксперименты");const t=a[this.currentRoute];t&&(e.innerHTML=`
      <div class="placeholder-view">
        <h2 class="placeholder-title">${t.title}</h2>
        <p class="placeholder-desc">${t.desc}</p>
      </div>
    `)}renderErrorBoundary(e){const t=this.container.querySelector("#app-main")||this.container;t.innerHTML=`
      <div class="error-panel" role="alert">
        <h2 class="error-title">Критическая ошибка интерфейса</h2>
        <p>Произошел сбой при отрисовке или маршрутизации представления. Пожалуйста, попробуйте восстановить сессию.</p>
        <div class="error-message">${e.stack||e.message}</div>
        <button class="btn-recovery" id="btn-recover">Сбросить и вернуться на главную</button>
      </div>
    `;const n=t.querySelector("#btn-recover");n&&n.addEventListener("click",()=>{window.location.href=`${window.location.origin}${window.location.pathname}#/prepare`})}}document.addEventListener("DOMContentLoaded",()=>{const r=document.getElementById("app");r&&new d(r).init()});
