import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { initTheme } from "./lib/theme.svelte";

const target = document.getElementById("app");
if (!target) throw new Error("missing #app element");

initTheme();

export default mount(App, { target });
