// The app's actions by name, so the assistant and the tour drive the same functions a person's clicks do. Each screen
// registers what it can do (app.js, plan.js); perform() runs one and throws an Error with a plain message if it
// cannot (for example, no plan is open yet).

const handlers = new Map();

export const ACTIONS = ["run_plan", "set_budget", "show_country", "show_language", "set_metric", "open_why",
  "open_report", "open_track_record", "start_tour", "reset_map", "go_start"];

/** Register the function for an action name: fn(action) may return a promise. */
export function register(name, fn) {
  handlers.set(name, fn);
}

export function can(name) {
  return handlers.has(name);
}

/** Run one action ({type, ...arguments}); resolves when it is done on screen. */
export async function perform(action) {
  const fn = handlers.get(action?.type);
  if (!fn) throw new Error(`Babel can't do "${action?.type}" here.`);
  return fn(action);
}
