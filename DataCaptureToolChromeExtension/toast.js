// // toast.js
function showToast(message, type = "info", duration = 3000) {
    const existingContainer = document.querySelector("#job-agent-toast-container");
    const container = existingContainer || createToastContainer();
  
    const toast = document.createElement("div");
    toast.className = `job-agent-toast ${type}`;
    toast.textContent = message;
  
    container.appendChild(toast);
  
    // Force reflow to trigger transition
    void toast.offsetWidth;
  
    // Start showing toast
    toast.classList.add("show");
  
    // Fade out after delay
    setTimeout(() => {
      toast.classList.remove("show");
      toast.classList.add("hide");
  
      // Remove from DOM after fade-out completes
      toast.addEventListener("transitionend", () => toast.remove());
    }, duration);
  }
  
  function createToastContainer() {
    const container = document.createElement("div");
    container.id = "job-agent-toast-container";
    document.body.appendChild(container);
    return container;
  }
  
  (function injectToastStyles() {
    if (document.getElementById("job-agent-toast-styles")) return;
  
    const style = document.createElement("style");
    style.id = "job-agent-toast-styles";
    style.textContent = `
      #job-agent-toast-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 99999;
        display: flex;
        flex-direction: column;
        gap: 12px;
        pointer-events: none;
      }
  
      .job-agent-toast {
        min-width: 220px;
        max-width: 300px;
        background-color: #333;
        color: white;
        padding: 10px 15px;
        border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        font-size: 14px;
        opacity: 0;
        transform: translateY(-10px);
        transition: opacity 0.4s ease, transform 0.4s ease;
        pointer-events: auto;
      }
  
      .job-agent-toast.show {
        opacity: 1;
        transform: translateY(0);
      }
  
      .job-agent-toast.hide {
        opacity: 0;
        transform: translateY(-20px);
      }
  
      .job-agent-toast.success { background-color: #4CAF50; }
      .job-agent-toast.error   { background-color: #f44336; }
      .job-agent-toast.warning { background-color: #ff9800; }
      .job-agent-toast.info    { background-color: #2196F3; }
    `;
    document.head.appendChild(style);
  })();
  