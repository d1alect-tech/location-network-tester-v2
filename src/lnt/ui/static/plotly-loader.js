export const PLOTLY_SOURCE = "/static/vendor/plotly-gl2d-3.7.0.min.js";

function isPlotly(value) {
  return typeof value?.newPlot === "function";
}

export function createPlotlyLoader({ documentRef, globalRef }) {
  let inFlight = null;

  return function loadPlotlyFromDocument() {
    if (isPlotly(globalRef.Plotly)) {
      return Promise.resolve(globalRef.Plotly);
    }
    if (inFlight !== null) {
      return inFlight;
    }

    const script = documentRef.createElement("script");
    script.src = PLOTLY_SOURCE;
    script.defer = true;
    script.dataset.lntPlotly = "true";

    inFlight = new Promise((resolve, reject) => {
      function rejectLoad(message) {
        script.remove();
        inFlight = null;
        reject(new Error(message));
      }

      script.onload = () => {
        if (!isPlotly(globalRef.Plotly)) {
          rejectLoad("Plotly загружен без доступной функции newPlot.");
          return;
        }
        resolve(globalRef.Plotly);
      };
      script.onerror = () => {
        rejectLoad(`Не удалось загрузить Plotly из ${PLOTLY_SOURCE}.`);
      };
    });

    documentRef.head.append(script);
    return inFlight;
  };
}

const browserLoader = typeof document === "undefined" || typeof window === "undefined"
  ? null
  : createPlotlyLoader({ documentRef: document, globalRef: window });

export function loadPlotly() {
  if (browserLoader === null) {
    return Promise.reject(new Error("Plotly доступен только в браузере."));
  }
  return browserLoader();
}
