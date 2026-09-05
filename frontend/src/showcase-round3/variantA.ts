/** R3-A «Стойка»: FSW-плотность — полный периметр, softkey-колонка справа,
 *  нейтральный графит, IBM Plex целиком. Бриф #13, оси: плотный периметр + Plex. */
import "../showcase-redesign/fonts/fonts.css";
import "./tokens.css";
import "./kit.css";
import "./variantA.css";
import { mountVariantA } from "./variantALayout";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");
document.body.classList.add("r3", "r3--a");
mountVariantA(app);
