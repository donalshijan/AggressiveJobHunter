
let isCapturing = false;
let rawActions = [];
let enrichedLearnableDOMDataAndInstructionsForInteraction = [];

let currentUIDToSelectorMap = new Map();
let currentSelectorToUIDMap = new Map();
let currentInteractables = [];

let debounceTimer = null;
let lastScrollY = window.scrollY;
let lastScrollCapturedY = window.scrollY;

let scrollables = [];
const scrollHandlers = new WeakMap();

const INTERACTABLE_TAGS = ["input", "button", "select", "textarea", "a"];

const FLATTEN_SEPARATOR = '->>';

let reverseValueToPlaceholder = {};

let isPausedForManualIntervention = null;

// Create debounced scroll handler once
let debouncedWindowScrollHandler = null;

function flattenObject(obj, parentKey = "", result = {}) {
  for (let key in obj) {
    if (!obj.hasOwnProperty(key)) continue;

    const value = obj[key];
    const newKey = parentKey ? `${parentKey}${FLATTEN_SEPARATOR}${key}` : key;

    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      flattenObject(value, newKey, result);
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => {
        if (typeof item === "object" && item !== null) {
          flattenObject(item, `${newKey}${FLATTEN_SEPARATOR}${index}`, result);
        } else {
          result[`${newKey}${FLATTEN_SEPARATOR}${index}`] = item;
        }
      });
    } else {
      result[newKey] = value;
    }
  }
  return result;
}

async function buildReverseMap(phase) {
  reverseValueToPlaceholder = {}; // reset previous map

  const phaseToFile = {
    signin: "applicant_credentials.json",
    search: "applicant_preferences.json",
    application: "applicant_data.json"
  };

  const file = phaseToFile[phase];
  if (!file) {
    // console.warn(`⚠️ Unknown capture phase: "${phase}"`);
    showToast(`⚠️ Unknown capture phase: "${phase}"`,'warning');
    return;
  }

  try {
    const res = await fetch(chrome.runtime.getURL(`data/${file}`));
    const json = await res.json();

    const flatJson = flattenObject(json);  // 👈 flatten nested structure

    for (const [key, value] of Object.entries(flatJson)) {
      if (typeof value === "string") {
        if (!reverseValueToPlaceholder[value]) {
          reverseValueToPlaceholder[value] = [];
        }
      
        const keyPlaceholder = `$${key}`;
        if (!reverseValueToPlaceholder[value].includes(keyPlaceholder)) {
          reverseValueToPlaceholder[value].push(keyPlaceholder);
        }
      }
    }

    // console.log(`✅ Reverse map built for phase "${phase}":`, reverseValueToPlaceholder);
    showToast(`✅ Reverse map built for phase: "${phase}"`,'success');
  } catch (e) {
    // console.error(`❌ Failed to load ${file}:`, e);
    showToast(`❌ Failed to load ${file}: ${e}`, 'error');
  }
}

window.startCapture = async (phase = "unspecified") => {
  window.capturePhase = phase;
  await buildReverseMap(window.capturePhase);
  isCapturing = true;
  rawActions = [];
  enrichedLearnableDOMDataAndInstructionsForInteraction = [];
  document.addEventListener("click", logClick, true);
  document.addEventListener("change", logInput, true);
  debouncedWindowScrollHandler = debounce((e) => logScroll(e, null), 1000);
  window.addEventListener("scroll", debouncedWindowScrollHandler, { passive: true });
  lastScrollY = window.scrollY;
  lastScrollCapturedY = window.scrollY;

  isPausedForManualIntervention = false;

  injectManualControlButtons()

  observeNavigationAndSubmissions();

  extractVisibleInteractablesAndBuildUidMapping();


  // console.log("✅ Capture started");
  showToast("✅ Capture started",'info');
};

window.stopCapture = () => {
  if (!isCapturing) return;
  isCapturing = false;

  document.removeEventListener("click", logClick, true);
  document.removeEventListener("change", logInput, true);
  window.removeEventListener("scroll", debouncedWindowScrollHandler);

  pushCurrentPageCapture(); // Push before exporting
  removeManualControlButtons();

  const blob = new Blob([
    JSON.stringify({ pages: enrichedLearnableDOMDataAndInstructionsForInteraction }, null, 2)
  ], { type: "application/json" });

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `instruction-${Date.now()}.json`;
  a.click();

  // console.log("📦 Final data saved");
  showToast("📦 Final data saved",'success');
  generatePhaseJsonFilesFromReverseMap();
};

function generatePhaseJsonFilesFromReverseMap() {
  const phaseToPrefix = {
    signin: "credentials",
    search: "preferences",
    application: "data"
  };
  const suffix = phaseToPrefix[window.capturePhase];
  if (!suffix) {
    // console.warn("⚠️ Unknown capture phase. Skipping export.");
    showToast("⚠️ Unknown capture phase. Skipping export.",'warning');
    return;
  }

  const flat = {};

  for (const [value, placeholders] of Object.entries(reverseValueToPlaceholder)) {
    for (const placeholder of placeholders) {
      // const match = placeholder.match(/^\$(\w+)$/); // extract field name like $email
      const match = placeholder.match(/^\$(.+)$/); // extract field name like $email and fields with . and numbers like $education.0.institute
      if (!match) continue;

      const field = match[1];
      flat[field] = value;
    }
  }

  // console.log("flat:",flat);
  // Rebuild nested structure
  const nested = unflattenObject(flat);

  // console.log('nested:',nested);
  // Download the relevant one based on current phase
  const fileName = `applicant_${suffix}.json`;
  const blob = new Blob(
    [JSON.stringify(nested, null, 2)],
    { type: "application/json" }
  );

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();

  // console.log(`💾 Exported ${fileName}`);
  showToast(`💾 Exported ${fileName}`,'success');
}

function unflattenObject(flat) {
  const result = {};

  for (const flatKey in flat) {
    const keys = flatKey.split(FLATTEN_SEPARATOR);
    let current = result;

    keys.forEach((key, index) => {
      const isLast = index === keys.length - 1;
      const nextKey = keys[index + 1];

      // Convert key to number if it looks like an array index
      const isArrayIndex = /^\d+$/.test(key);
      const realKey = isArrayIndex ? parseInt(key, 10) : key;

      if (isLast) {
        current[realKey] = flat[flatKey];
      } else {
        if (!current[realKey]) {
          // Decide whether to make an array or an object
          current[realKey] = /^\d+$/.test(nextKey) ? [] : {};
        }
        current = current[realKey];
      }
    });
  }

  return result;
}



function logClick(e) {
  if (!isCapturing) return;
  if (isPausedForManualIntervention) return;
  const selector = getDomPath(e.target);
  const uid = currentSelectorToUIDMap.get(selector);
  if (!uid) return;

  rawActions.push({ action: "click", id : uid,  });
  showToast("click captured",'info');
}

function logInput(e) {
  if (!isCapturing) return;
  if (isPausedForManualIntervention) return;
  const selector = getDomPath(e.target);
  const uid = currentSelectorToUIDMap.get(selector);
  if (!uid) return;
  let value = e.target.value;
  let placeholder = reverseValueToPlaceholder[value];
  if (!placeholder) {
    // Create new key name from the input's name or placeholder
    const keyGuess = inferKeyName(e.target);
    placeholder = `$${keyGuess}`;
    
    // Update reverse map
    reverseValueToPlaceholder[value] = placeholder;
  }

  rawActions.push({
    action: "fill",
    id : uid,
    value: placeholder,
  });
  showToast("input captured",'info');
}

function logScroll(e, el = null) {
  if (!isCapturing) return;
  if (isPausedForManualIntervention) return;
  const isWindowScroll = !el;
  const target = isWindowScroll ? window : el;
  const scrollTop = isWindowScroll ? window.scrollY : el.scrollTop;
  const last = isWindowScroll ? lastScrollCapturedY : (el._lastScrollTop || 0);
  const deltaY = scrollTop - last;

  if (Math.abs(deltaY) < 10) return;

  const selector = isWindowScroll ? "window" : getDomPath(el);
  const uid = isWindowScroll ? "window" : currentSelectorToUIDMap.get(selector) || "unknown";

  rawActions.push({
    action: "scroll",
    deltaY,
    scrollTo: scrollTop,
    id: uid,
    source: isWindowScroll ? "window" : "element"
  });

  // Update scroll positions
  if (isWindowScroll) {
    lastScrollCapturedY = scrollTop;
  } else {
    el._lastScrollTop = scrollTop;
  }

  pushCurrentPageCapture();
  console.log("🌀 Scroll logged:", {
    source: isWindowScroll ? "window" : "element",
    uid,
    deltaY,
    scrollTo: scrollTop
  });
  showToast("🌀 Scroll logged:",'info');
  extractVisibleInteractablesAndBuildUidMapping();
}

function inferKeyName(el) {
  const labelText = getLabelText(el);
  if (labelText) return sanitizeKey(labelText);

  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel) return ariaLabel;

  const placeholder = el.getAttribute("placeholder");
  if (placeholder) return sanitizeKey(placeholder);

  return "unknown_field";
}

function sanitizeKey(text) {
  return text.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^\w]/g, "");
}

function debounce(fn, delay) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function throttle(fn, limit) {
  let inThrottle = false;
  return function (...args) {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

function attachScrollListeners() {
  scrollables.forEach(el => {
    const handler = scrollHandlers.get(el);
    if (handler) el.removeEventListener('scroll', handler);
  });
  scrollables.length = 0;
  const newScrollables = Array.from(document.querySelectorAll('*')).filter(el => {
    const style = getComputedStyle(el);
    return ['auto', 'scroll'].includes(style.overflowY) && el.scrollHeight > el.clientHeight;
  });

  newScrollables.forEach(el => {
    const handler = debounce((e) => logScroll(e, el), 300);
    scrollHandlers.set(el, handler);
    el.addEventListener('scroll', handler, { passive: true });
    scrollables.push(el);
  });

  // console.log("✅ Attached scroll listeners:", scrollables.length);
  showToast(`✅ Attached scroll listeners: ${scrollables.length}`, 'success');
}

function detachScrollListeners() {
  scrollables.forEach(el => {
    const handler = scrollHandlers.get(el);
    if (handler) el.removeEventListener('scroll', handler);
    scrollHandlers.delete(el);
  });
  scrollables.length = 0;
  scrollables = [];
}

function extractVisibleInteractablesAndBuildUidMapping() {
  attachScrollListeners();
  currentUIDToSelectorMap.clear();
  currentSelectorToUIDMap.clear();
  currentInteractables = [];

  const allElements = document.querySelectorAll("*");
  let uidCounter = 0;

  allElements.forEach((el) => {
    if (!isElementInteractable(el) || !isVisible(el)) return;

    const rect = el.getBoundingClientRect();
    if (
      rect.width === 0 || rect.height === 0 ||
      rect.bottom < 0 || rect.top > window.innerHeight ||
      rect.right < 0 || rect.left > window.innerWidth
    ) return;

    const selector = getDomPath(el);
    const uid = `el_${uidCounter++}`;

    currentUIDToSelectorMap.set(uid, selector);
    currentSelectorToUIDMap.set(selector, uid);

    currentInteractables.push({
      uid,
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || el.value || "").trim(),
      name: el.getAttribute("name") || null,
      type: el.getAttribute("type") || null,
      inputMode: el.getAttribute("inputmode") || null,
      autocomplete: el.getAttribute("autocomplete") || null,
      ariaLabel: el.getAttribute("aria-label") || null,
      placeholder: el.getAttribute("placeholder") || null,
      alt: el.getAttribute("alt") || null,
      role: el.getAttribute("role") || null,
      label: getLabelText(el),
      dataAttrs: getDataAttributes(el),
      options: getOptions(el),
    });
  });
}

function pushCurrentPageCapture() {
  if (currentInteractables.length === 0) return;

  const dedupedFills = {};
  const finalActions = [];

  for (const act of rawActions) {
    if (act.action === "fill") {
      dedupedFills[act.id] = act;
    } else {
      finalActions.push(act);
    }
  }

  finalActions.push(...Object.values(dedupedFills));

  if (finalActions.length === 0) {
    // console.log("🟡 Skipping page capture (no actions)");
    showToast("🟡 Skipping page capture (no actions)",'info');
    return;
  }

  enrichedLearnableDOMDataAndInstructionsForInteraction.push({
    interactables: currentInteractables,
    phase: window.capturePhase,
    scrollY: window.scrollY,
    actions: finalActions
  });

  rawActions = [];
  currentInteractables = [];
}

function observeNavigationAndSubmissions() {
  const observer = new MutationObserver((mutations) => {
    if (isPausedForManualIntervention) return false;
    const hasNavigation = mutations.some(m => {
      if (m.target.closest?.("#job-agent-toast-container")) return false;
      m.type === "childList" || m.type === "attributes";
    });
    if (hasNavigation && isCapturing) {
      clearTimeout(debounceTimer); // safe even if debounceTimer is null
      debounceTimer = setTimeout(() => {
        pushCurrentPageCapture();
        extractVisibleInteractablesAndBuildUidMapping();
      }, 500);
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true
  });

  // Also detect form submissions
  document.addEventListener("submit", () => {
    if (isCapturing) {
      pushCurrentPageCapture();
      setTimeout(() => extractVisibleInteractablesAndBuildUidMapping(), 500);
    }
  }, true);
}

// === Helper Functions ===

function isElementInteractable(el) {
  const tag = el.tagName.toLowerCase();
  if (INTERACTABLE_TAGS.includes(tag)) return true;

  const role = el.getAttribute("role");
  const tabindex = el.getAttribute("tabindex");

  if (
    typeof el.onclick === "function" ||
    el.hasAttribute("onclick") ||
    (role && ["button", "link", "checkbox", "radio", "switch"].includes(role.toLowerCase())) ||
    (tabindex !== null && parseInt(tabindex) >= 0)
  ) return true;

  const style = getComputedStyle(el);
  const isScrollable =
    ['auto', 'scroll'].includes(style.overflowY) &&
    el.scrollHeight > el.clientHeight;
  return isScrollable;
}

function isVisible(el) {
  const style = window.getComputedStyle(el);
  return (
    style &&
    style.display !== "none" &&
    style.visibility !== "hidden" &&
    style.opacity !== "0" &&
    style.pointerEvents !== "none"
  );
}

function getDomPath(el) {
  if (!el) return "";
  let stack = [];
  while (el.parentNode != null) {
    let sibCount = 0;
    let sibIndex = 0;
    for (let i = 0; i < el.parentNode.childNodes.length; i++) {
      let sib = el.parentNode.childNodes[i];
      if (sib.nodeName === el.nodeName) {
        if (sib === el) sibIndex = sibCount;
        sibCount++;
      }
    }
    const tagName = el.nodeName.toLowerCase();
    const selector = sibCount > 1 ? `${tagName}:nth-of-type(${sibIndex + 1})` : tagName;
    stack.unshift(selector);
    el = el.parentNode;
  }
  return stack.slice(1).join(" > ");
}

function getOptions(el) {
  if (el.tagName.toLowerCase() === "select") {
    return Array.from(el.options).map(opt => opt.text);
  }
  if (el.type === "radio" || el.type === "checkbox") {
    return [el.value || el.name];
  }
  return null;
}

function getDataAttributes(el) {
  const data = {};
  for (const attr of el.attributes) {
    if (attr.name.startsWith("data-")) {
      data[attr.name] = attr.value;
    }
  }
  return Object.keys(data).length > 0 ? data : null;
}

function getLabelText(el) {
  if (!el) return null;

  // Case 1: label[for=input.id]
  if (el.id) {
    const label = document.querySelector(`label[for="${el.id}"]`);
    if (label) return label.innerText.trim();
  }

  // Case 2: <label><input> Text </label>
  let parent = el.parentElement;
  while (parent) {
    if (parent.tagName.toLowerCase() === "label") {
      return parent.innerText.trim();
    }
    parent = parent.parentElement;
  }

  return null;
}

function injectManualControlButtons() {
  const container = document.createElement("div");
  container.id = "manual-control-buttons";
  container.style.position = "fixed";
  container.style.bottom = "100px";
  container.style.right = "20px";
  container.style.zIndex = 999999;
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.gap = "10px";

  const interveneBtn = document.createElement("button");
  interveneBtn.textContent = "➕ Intervene Instruction";
  interveneBtn.style.padding = "8px";
  interveneBtn.style.backgroundColor = "#ff9800";
  interveneBtn.style.color = "#fff";
  interveneBtn.style.border = "none";
  interveneBtn.style.borderRadius = "5px";
  interveneBtn.style.cursor = "pointer";

  const continueBtn = document.createElement("button");
  continueBtn.textContent = "▶️ Continue Capture";
  continueBtn.style.padding = "8px";
  continueBtn.style.backgroundColor = "#4caf50";
  continueBtn.style.color = "#fff";
  continueBtn.style.border = "none";
  continueBtn.style.borderRadius = "5px";
  continueBtn.style.cursor = "pointer";
  continueBtn.disabled = true;

  // Handlers
  interveneBtn.onclick = () => {
    pauseCaptureForManualInstruction();
    continueBtn.disabled = false;
    interveneBtn.disabled = true;
  };

  continueBtn.onclick = () => {
    resumeCaptureAfterManualInstruction();
    continueBtn.disabled = true;
    interveneBtn.disabled = false;
  };

  container.appendChild(interveneBtn);
  container.appendChild(continueBtn);
  document.body.appendChild(container);
}

function pauseCaptureForManualInstruction() {
  isPausedForManualIntervention = true;
  showToast("✋ Capture paused for manual instruction", "info");

  // You can insert a blank instruction manually or wait for user to do something
  rawActions.push({
    action: "intervene",
    message: "manual intervention needed",
  });
  
  pushCurrentPageCapture();

}

function resumeCaptureAfterManualInstruction() {
  isPausedForManualIntervention = false;

  // extractVisibleInteractablesAndBuildUidMapping();
  showToast("▶️ Capture resumed", "success");
}

function removeManualControlButtons() {
  const el = document.getElementById("manual-control-buttons");
  if (el) el.remove();
}