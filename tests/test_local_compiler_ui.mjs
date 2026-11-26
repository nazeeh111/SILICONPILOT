// Evaluate the shipped browser handlers with a controlled request queue.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createContext, runInContext } from "node:vm";

const source = readFileSync(new URL("../observatory/app.js", import.meta.url), "utf8");

class Element extends EventTarget {
  classList = { add() {}, remove() {}, toggle() {} };
  children = [];
  value = "";
  open = false;
  hidden = false;
  disabled = false;
  checked = false;
  textContent = "";
  innerHTML = "";

  get selectedOptions() {
    return this.children.filter((option) => option.value === this.value);
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
  }
}

function harness() {
  const elements = new Map();
  const requests = [];
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = createContext({
    URL,
    location: new URL("http://127.0.0.1:8791/"),
    window: new EventTarget(),
    document: {
      getElementById: get,
      querySelectorAll: () => [],
      createElement: () => new Element(),
    },
    fetch(url, options) {
      // The corpus rendering is exercised by browser tests. Only admit exact local POSTs here.
      if (url === "data/observatory.json") return new Promise(() => {});
      if (url === "/api/health") return Promise.resolve({ ok: true, json: async () => ({ mode: "local" }) });
      assert.equal(url, "/api/compile");
      assert.equal(options.method, "POST");
      return new Promise((resolve) => requests.push({ resolve, input: JSON.parse(options.body) }));
    },
  });
  runInContext(source, context);
  runInContext(`state.data = {
    models: [
      { id: "banknote-4x4x2", name: "4 × 4 × 2" },
      { id: "banknote-4x12x2", name: "4 × 12 × 2" },
    ],
  }`, context);
  const choose = (width, parallelism) => runInContext(`state.selected = {
    model_id: "banknote-4x${width}x2",
    config: { bits: 8, fractional_bits: 5, accumulator_bits: 24, parallelism: ${parallelism}, buffering: 1 },
  }`, context);
  const trigger = (id, type = "click") => get(id).dispatchEvent(new Event(type, { cancelable: true }));
  const deliver = async (request, response) => {
    request.resolve(response);
    await new Promise((resolve) => setImmediate(resolve));
  };
  const success = (name) => ({
    ok: true,
    json: async () => ({ verification: { passed: true, samples: 78 }, artifact_base: `/api/artifacts/${name}/` }),
  });
  return { get, choose, trigger, requests, deliver, success };
}

test("a delayed result cannot appear in a reopened compiler with another model", async () => {
  const { get, choose, trigger, requests, deliver, success } = harness();
  choose(4, 1);
  trigger("local-compile-toggle");
  trigger("local-compile-form", "submit");
  trigger("local-compile-close");
  choose(12, 2);
  trigger("local-compile-toggle");

  const result = get("local-compile-result");
  assert.equal(get("compile-model").value, "banknote-4x12x2");
  assert.equal(requests[0].input.model_id, "banknote-4x4x2");
  assert.equal(requests[0].input.config.parallelism, 1);
  assert.equal(get("local-compile-submit").disabled, true);
  trigger("local-compile-form", "submit");
  assert.equal(requests.length, 1);

  await deliver(requests[0], success("older"));
  assert.equal(result.hidden, true);
  assert.doesNotMatch(result.innerHTML, /Fresh RTL/);
  assert.equal(get("local-compile-submit").disabled, false);

  trigger("local-compile-form", "submit");
  assert.equal(requests[1].input.model_id, "banknote-4x12x2");
  assert.equal(requests[1].input.config.parallelism, 2);
  await deliver(requests[1], success("newer"));
  assert.equal(result.hidden, false);
  assert.match(result.innerHTML, /4 × 12 × 2 · 2 MAC lanes/);
  assert.equal(result.children[0].href, "http://127.0.0.1:8791/api/artifacts/newer/design.v");
});

test("editing the configuration suppresses an obsolete request error", async () => {
  const { get, choose, trigger, requests, deliver } = harness();
  choose(4, 1);
  trigger("local-compile-toggle");
  trigger("local-compile-form", "submit");
  get("compile-parallelism").value = "3";
  trigger("local-compile-form", "input");
  await deliver(requests[0], { ok: false, status: 400, json: async () => ({ error: "obsolete failure" }) });
  assert.equal(get("local-compile-result").hidden, true);
  assert.doesNotMatch(get("local-compile-result").textContent, /obsolete failure/);
  assert.equal(get("local-compile-submit").disabled, false);
});
