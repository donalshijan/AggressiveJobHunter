// execute script directly
// document.getElementById("start").addEventListener("click", async () => {
//     const phase = document.getElementById("phaseSelect").value;
//     const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
//     chrome.scripting.executeScript({
//       target: { tabId: tab.id },
//       func: (selectedPhase) => {
//         window.startCapture?.(selectedPhase);
//       },
//       args: [phase]
//     });
//   });
  
//   document.getElementById("stop").addEventListener("click", async () => {
//     const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
//     chrome.scripting.executeScript({
//       target: { tabId: tab.id },
//       function: () => window.stopCapture?.()
//     });
//   });
  

  // Send message to background script to start capture

document.getElementById("start").addEventListener("click", () => {
  const phase = document.getElementById("phaseSelect").value;
  chrome.runtime.sendMessage({ action: "start-capture", phase });
});

// Send message to background script to stop capture
document.getElementById("stop").addEventListener("click", () => {
  chrome.runtime.sendMessage({ action: "stop-capture" });
});